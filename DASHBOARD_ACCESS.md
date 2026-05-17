# 🌐 Dashboard Access Guide

## 📍 URL Dashboard

### Dari Laptop/PC (via USB Tethering)
```
http://10.42.0.1:5000
```

### Dari RPi5 Sendiri
```
http://localhost:5000
```

### Auto-detect IP
Script `start_all.sh` akan otomatis menampilkan IP yang benar saat startup.

---

## 🚀 Quick Start

```bash
# 1. Start sistem
cd ~/thesis
sudo ./start_all.sh

# 2. Tunggu 5-10 detik

# 3. Buka browser di laptop/PC
# URL: http://10.42.0.1:5000
```

---

## 📊 Dashboard Features

### Real-time Monitoring
- 📈 **pH & Temperature Chart** (dual-axis, auto-refresh 2s)
- 🌐 **Network Performance**
  - Latency (ms)
  - Packet Loss (%)
  - Throughput (Mbps)
  - Packets Sent/Dropped
  - Uptime (hours)
- 📡 **5G Core Status** (AMF, SMF, UPF)
- 🔒 **IPsec Tunnel Status** (ESTABLISHED/DOWN)
- 🤖 **AI Control**
  - Phase (RB/FQL/DQN)
  - Action (OFF/LOW/MED/HIGH)
  - Reward
  - Real Steps
  - Buffer Size
  - Epsilon

### UI Features
- 🎨 Professional dark theme
- 📱 Responsive design
- 🔄 Auto-refresh every 2 seconds
- 🛡️ Graceful error handling
- ⚡ Real-time Chart.js graphs

---

## 🔍 Troubleshooting

### Dashboard tidak bisa diakses

**1. Cek apakah dashboard running**
```bash
ps aux | grep dashboard.py
```

**2. Cek port 5000**
```bash
sudo netstat -tulpn | grep 5000
```

**3. Cek log dashboard**
```bash
tail -f results/dashboard.log
```

**4. Cek IP RPi5**
```bash
hostname -I
# Output: 10.42.0.1 ...
```

**5. Test dari RPi5**
```bash
curl http://localhost:5000
# Harus return HTML
```

### Dashboard muncul tapi data kosong

**1. Cek apakah run_real.py running**
```bash
ps aux | grep run_real.py
tail -f results/run_real.log
```

**2. Cek apakah Pico 2W terhubung**
```bash
tail -f results/hasil_real/pico_monitor.log
```

**3. Cek state.json**
```bash
cat results/hasil_real/state.json
```

### Network stats tidak muncul

**1. Cek apakah callbox running**
```bash
ps aux | grep callbox
tail -f results/callbox.log
```

**2. Cek network stats file**
```bash
cat results/network/callbox_stats.json
```

**3. Cek IPsec tunnel**
```bash
sudo ipsec statusall | grep ESTABLISHED
```

---

## 🔄 Restart Dashboard Only

Jika hanya dashboard yang bermasalah (tanpa restart semua):

```bash
# 1. Kill dashboard
pkill -f dashboard.py

# 2. Start ulang dashboard
cd ~/thesis
python3 main/real/dashboard.py > results/dashboard.log 2>&1 &

# 3. Cek log
tail -f results/dashboard.log
```

---

## 📱 Access dari Device Lain

### Dari Smartphone (via WiFi)

Jika RPi5 terhubung ke WiFi yang sama dengan smartphone:

```bash
# Cek IP WiFi RPi5
hostname -I
# Contoh output: 10.42.0.1 192.168.1.100

# Akses dari smartphone browser
http://192.168.1.100:5000
```

### Dari Laptop via SSH Tunnel

Jika akses remote via SSH:

```bash
# Di laptop
ssh -L 5000:localhost:5000 ubuntu@10.42.0.1

# Buka browser di laptop
http://localhost:5000
```

---

## 🎯 Expected Behavior

### Saat Pertama Start (0-10 detik)
```
✅ Dashboard muncul dengan UI lengkap
⚠️ Network stats: "Network stats not available yet"
⚠️ Status: UNKNOWN
⏳ pH & Temperature: Waiting for Pico 2W
```

### Setelah 10-30 detik
```
✅ Network stats muncul (latency, packet loss, throughput)
✅ IPsec status: ESTABLISHED
✅ pH & Temperature: Data real dari Pico 2W
✅ Grafik mulai terisi
```

### Normal Operation
```
✅ Grafik pH & Temperature update setiap 2 detik
✅ Network stats update setiap 2 detik
✅ AI control info update real-time
✅ 5G Core status: RUNNING
✅ IPsec tunnel: ESTABLISHED
```

---

## 📸 Screenshot Checklist

Untuk paper/thesis, ambil screenshot:

- [ ] Dashboard overview (full page)
- [ ] pH & Temperature chart (zoomed)
- [ ] Network performance section
- [ ] 5G Core status
- [ ] AI control metrics
- [ ] IPsec tunnel status: ESTABLISHED

---

## 🔗 Related Files

- **Dashboard Code**: `main/real/dashboard.py`
- **Start Script**: `start_all.sh`
- **Dashboard Log**: `results/dashboard.log`
- **State Data**: `results/hasil_real/state.json`
- **Network Stats**: `results/network/callbox_stats.json`

---

## 📞 Quick Commands

```bash
# Start
sudo ./start_all.sh

# Stop
sudo ./stop_all.sh

# Dashboard log
tail -f results/dashboard.log

# Main log
tail -f results/run_real.log

# Network stats
cat results/network/callbox_stats.json | python3 -m json.tool

# IPsec status
sudo ipsec statusall | grep ESTABLISHED
```

---

## ✅ Summary

**Dashboard URL:** `http://10.42.0.1:5000`

**Features:**
- Real-time pH & Temperature charts
- Network performance monitoring
- 5G Core status
- IPsec tunnel status
- AI control metrics
- Professional dark theme
- Auto-refresh every 2 seconds

**Robust:**
- Tidak crash jika data belum tersedia
- Graceful error handling
- Auto-recovery

**Access:** Buka browser, ketik `http://10.42.0.1:5000` 🚀
