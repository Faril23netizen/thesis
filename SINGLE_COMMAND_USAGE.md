# 🚀 Cara Pakai Sistem - Super Simple!

## ⚡ 3 Command Aja!

```bash
# 1. Start semua (Callbox + N3IWF + Edge AI + Dashboard)
sudo ./start_all.sh

# 2. Tinggal semalaman (atau manual stop)
# Buka browser: http://10.42.0.1:5000

# 3. Stop dan analisis
sudo ./stop_all.sh
python3 analyze_all.py
```

**Selesai!** Semua jalan otomatis, data terkumpul, grafik lengkap.

---

## 📋 Yang Terjadi Otomatis

**`start_all.sh` jalankan:**
1. Callbox 5G Simulator (AMF, SMF, UPF)
2. N3IWF Client (IPsec tunnel)
3. run_real.py (Progressive AI: RB → FQL → DQN)
4. Dashboard (Port 5000)

**`stop_all.sh` hentikan:**
- Semua service
- IPsec tunnel
- Logs & data tetap tersimpan

**`analyze_all.py` buat:**
- PDF: `results/thesis/complete_analysis.pdf` (6 grafik + 1 tabel network)
- CSV: `results/thesis/summary.csv`
- Plots: `results/thesis/plots/*.png` (7 files)

---

## 🖥️ Akses

- **Dashboard:** `http://10.42.0.1:5000`
- **TCP Server:** Port `5005` (Pico 2W)

---

## 📊 File Output

```
results/
├── thesis/
│   ├── complete_analysis.pdf   # ⭐ PDF lengkap
│   ├── summary.csv             # ⭐ Statistik
│   └── plots/*.png             # ⭐ Grafik individual
│
├── hasil_real/
│   └── comparison.csv          # Data mentah
│
└── *.log                       # Logs
```

---

## 🔍 Monitoring

```bash
# Lihat log
tail -f results/run_real.log

# Cek IPsec
sudo ipsec statusall | grep ESTABLISHED

# Cek data
tail -f results/hasil_real/comparison.csv

# Dashboard
http://10.42.0.1:5000
```

---

## 🐛 Troubleshooting

**Pico ga connect:**
```bash
ping 10.42.0.206
sudo netstat -tulpn | grep 5005
```

**Dashboard ga bisa dibuka:**
```bash
sudo ufw allow 5000/tcp
tail -f results/dashboard.log
```

**IPsec error:**
```bash
sudo ipsec restart
sudo ipsec statusall | grep ESTABLISHED
```

**Restart semua:**
```bash
sudo ./stop_all.sh
sleep 5
sudo ./start_all.sh
```

---

## ⏱️ Timeline

- **Startup:** 30 detik
- **Rule-Based:** 100 steps
- **FQL Training:** 200 steps
- **DQN:** Seterusnya

**Rekomendasi:** Jalankan semalaman (8-12 jam)

---

## 🎯 Untuk Thesis/Paper

**Grafik yang dihasilkan:**
1. Water Quality (pH & Temperature)
2. Progressive Learning (RB → FQL → DQN)
3. Action Distribution
4. Phase Comparison
5. Energy Consumption
6. Network Performance (Enhanced - Latency, Jitter, Packet Loss, Throughput)
7. **Network Details Table** ⭐ (IPsec, 5G Core, Packet Stats)

**Claim yang bisa dibuat:**
- ✅ Edge AI on Raspberry Pi 5
- ✅ N3IWF Integration with 5G Core (AMF, SMF, UPF)
- ✅ IPsec Secure Communication (10-15ms latency)
- ✅ Progressive Learning (RB → FQL → DQN)
- ✅ Real-time Monitoring Dashboard
- ✅ Network Reliability (packet loss ~1%)
- ✅ 5G Core Components Running

**Note:** Untuk comparison RB vs FQL vs DQN yang fair, gunakan hasil simulasi (steps sama).

---

## ✅ Checklist Sebelum Run

- [ ] RPi5 IP: `10.42.0.1`
- [ ] Pico IP: `10.42.0.206`
- [ ] strongSwan installed: `ipsec version`
- [ ] Python packages: `pip3 install flask numpy matplotlib`
- [ ] Scripts executable: `chmod +x start_all.sh stop_all.sh`

---

**Author:** Faril  
**Date:** 2026-05-17  
**Version:** 1.0 - Single Command System
