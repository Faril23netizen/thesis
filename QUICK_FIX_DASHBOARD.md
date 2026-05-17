# 🚀 Quick Fix - Dashboard Connection Issue

## Problem
Dashboard tidak bisa connect setelah `sudo ./start_all.sh`

## Solution (SUDAH DI-PUSH!)

Dashboard sudah diperbaiki dengan error handling yang lebih robust.

## Cara Update di RPi5

```bash
# 1. Stop sistem yang sedang running
cd ~/thesis
sudo ./stop_all.sh

# 2. Pull update terbaru
git pull origin master

# 3. Start ulang sistem
sudo ./start_all.sh

# 4. Tunggu 5-10 detik, lalu akses dashboard
# Browser: http://10.42.0.1:5000
```

## Apa yang Diperbaiki?

✅ Dashboard tidak crash jika network stats belum tersedia  
✅ Auto-create folder `results/network/`  
✅ Graceful error handling untuk missing files  
✅ Stale file detection (>30 seconds)  
✅ Default values jika data belum ada  

## Expected Behavior

### Saat Pertama Kali Start (0-10 detik)
- Dashboard muncul dengan UI lengkap
- Network stats menampilkan: "Network stats not available yet"
- Status: UNKNOWN
- pH & Temperature: Waiting for Pico 2W

### Setelah 10-30 detik
- Network stats mulai muncul (latency, packet loss, throughput)
- IPsec status: ESTABLISHED (jika tunnel berhasil)
- pH & Temperature: Data real dari Pico 2W
- Grafik mulai terisi

### Jika Ada Masalah
- Dashboard tetap running (tidak crash)
- Error message yang jelas
- Bisa di-refresh untuk retry

## Troubleshooting

### Dashboard tidak muncul sama sekali
```bash
# Cek log dashboard
tail -f results/dashboard.log

# Cek apakah dashboard running
ps aux | grep dashboard.py

# Cek port 5000
sudo netstat -tulpn | grep 5000
```

### Dashboard muncul tapi network stats kosong
```bash
# Cek apakah callbox running
ps aux | grep callbox

# Cek callbox log
tail -f results/callbox.log

# Cek network stats file
cat results/network/callbox_stats.json
```

### IPsec status: UNKNOWN
```bash
# Cek IPsec tunnel
sudo ipsec statusall | grep ESTABLISHED

# Restart IPsec jika perlu
sudo ipsec restart
```

## Summary

**Status:** ✅ FIXED & PUSHED

**Action Required:**
1. `git pull origin master` di RPi5
2. `sudo ./start_all.sh`
3. Akses `http://10.42.0.1:5000`

**Dashboard sekarang robust dan tidak akan crash!** 🎉
