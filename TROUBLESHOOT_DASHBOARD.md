# 🔧 Troubleshooting Dashboard Connection

## ⚠️ Problem: Dashboard tidak bisa diakses

### Kemungkinan Penyebab

1. **Dashboard process crashed** (paling sering)
2. **Port 5000 sudah dipakai**
3. **Python import error**
4. **PYTHONPATH tidak di-set**
5. **Firewall blocking port 5000**

---

## 🔍 Diagnosa Step-by-Step

### Step 1: Cek apakah dashboard running

```bash
ps aux | grep dashboard.py
```

**Expected output:**
```
ubuntu    6613  ... python3 main/real/dashboard.py
```

**Jika TIDAK ada output:**
- ❌ Dashboard tidak running (crashed atau tidak start)
- Lanjut ke Step 2

**Jika ADA output:**
- ✅ Dashboard running
- Lanjut ke Step 3

---

### Step 2: Cek dashboard log untuk error

```bash
tail -f results/dashboard.log
```

**Kemungkinan error:**

#### Error 1: ModuleNotFoundError
```
ModuleNotFoundError: No module named 'flask'
```

**Solusi:**
```bash
pip3 install --break-system-packages flask numpy matplotlib
```

#### Error 2: Permission denied (port 5000)
```
OSError: [Errno 13] Permission denied
```

**Solusi:**
```bash
# Gunakan port lain atau jalankan dengan sudo
sudo python3 main/real/dashboard.py
```

#### Error 3: Address already in use
```
OSError: [Errno 98] Address already in use
```

**Solusi:**
```bash
# Kill process yang pakai port 5000
sudo lsof -ti:5000 | xargs kill -9

# Atau restart sistem
sudo ./stop_all.sh
sudo ./start_all.sh
```

#### Error 4: Import error (PYTHONPATH)
```
ModuleNotFoundError: No module named 'fql'
```

**Solusi:**
```bash
# Set PYTHONPATH dan start ulang
export PYTHONPATH=/home/ubuntu/thesis:$PYTHONPATH
python3 main/real/dashboard.py
```

---

### Step 3: Cek port 5000

```bash
sudo netstat -tulpn | grep 5000
```

**Expected output:**
```
tcp  0  0  0.0.0.0:5000  0.0.0.0:*  LISTEN  6613/python3
```

**Jika TIDAK ada output:**
- ❌ Dashboard tidak listening di port 5000
- Cek dashboard log (Step 2)

**Jika ADA output:**
- ✅ Port 5000 listening
- Lanjut ke Step 4

---

### Step 4: Test dari localhost

```bash
curl http://localhost:5000
```

**Expected output:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>Aquaculture Dashboard</title>
...
```

**Jika dapat HTML:**
- ✅ Dashboard responding
- Problem mungkin di network/firewall
- Lanjut ke Step 5

**Jika error:**
```
curl: (7) Failed to connect to localhost port 5000: Connection refused
```
- ❌ Dashboard tidak responding
- Restart dashboard (lihat Quick Fix)

---

### Step 5: Test dari IP eksternal

```bash
# Dari laptop/PC
curl http://10.42.0.1:5000
```

**Jika berhasil:**
- ✅ Dashboard accessible dari luar
- Buka browser: http://10.42.0.1:5000

**Jika gagal:**
- ❌ Firewall atau network issue
- Cek firewall (Step 6)

---

### Step 6: Cek firewall

```bash
# Cek status firewall
sudo ufw status

# Jika active, allow port 5000
sudo ufw allow 5000/tcp
```

---

## 🚀 Quick Fix

### Fix 1: Restart Dashboard Only

```bash
# Kill dashboard
pkill -f dashboard.py

# Start ulang dengan PYTHONPATH
cd ~/thesis
PYTHONPATH=/home/ubuntu/thesis python3 main/real/dashboard.py > results/dashboard.log 2>&1 &

# Cek log
tail -f results/dashboard.log
```

### Fix 2: Restart Semua

```bash
cd ~/thesis
sudo ./stop_all.sh
sudo ./start_all.sh
```

### Fix 3: Manual Start (untuk debugging)

```bash
cd ~/thesis
export PYTHONPATH=/home/ubuntu/thesis
python3 main/real/dashboard.py
```

**Expected output:**
```
======================================================================
  🐟 Aquaculture Professional Dashboard
======================================================================
  Dashboard  : http://10.42.0.1:5000
  Features   : Real-time charts, Network monitoring, 5G Core status

  Make sure system is running: sudo ./start_all.sh
======================================================================

 * Serving Flask app 'dashboard'
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.42.0.1:5000
```

---

## 🔍 Diagnosa Otomatis

Jalankan script diagnosa:

```bash
cd ~/thesis
chmod +x diagnose_dashboard.sh
./diagnose_dashboard.sh
```

Script akan cek:
1. Dashboard process running?
2. Port 5000 listening?
3. Dashboard log ada error?
4. run_real.py running?
5. state.json tersedia?
6. Network stats tersedia?
7. Localhost connection OK?
8. Python packages installed?
9. PYTHONPATH set?

---

## 📋 Checklist Troubleshooting

- [ ] Dashboard process running? (`ps aux | grep dashboard.py`)
- [ ] Port 5000 listening? (`sudo netstat -tulpn | grep 5000`)
- [ ] Dashboard log OK? (`tail -f results/dashboard.log`)
- [ ] No import errors? (cek log)
- [ ] PYTHONPATH set? (`echo $PYTHONPATH`)
- [ ] Localhost responds? (`curl http://localhost:5000`)
- [ ] External IP responds? (`curl http://10.42.0.1:5000`)
- [ ] Firewall allows port 5000? (`sudo ufw status`)

---

## 🎯 Common Issues & Solutions

### Issue 1: "Dashboard tidak muncul sama sekali"

**Diagnosa:**
```bash
ps aux | grep dashboard.py
tail -f results/dashboard.log
```

**Solusi:**
```bash
# Restart dashboard
pkill -f dashboard.py
cd ~/thesis
PYTHONPATH=/home/ubuntu/thesis python3 main/real/dashboard.py > results/dashboard.log 2>&1 &
```

---

### Issue 2: "Dashboard muncul tapi data kosong"

**Diagnosa:**
```bash
# Cek run_real.py
ps aux | grep run_real.py
tail -f results/run_real.log

# Cek state.json
cat results/hasil_real/state.json
```

**Solusi:**
- Tunggu 10-30 detik untuk data muncul
- Pastikan Pico 2W terhubung: `ping 10.42.0.206`
- Cek run_real.log untuk error

---

### Issue 3: "Network stats tidak muncul"

**Diagnosa:**
```bash
# Cek callbox
ps aux | grep callbox
tail -f results/callbox.log

# Cek network stats
cat results/network/callbox_stats.json
```

**Solusi:**
- Tunggu 10-30 detik untuk callbox membuat stats
- Dashboard akan show "Network stats not available yet" (ini normal)
- Setelah callbox running, stats akan muncul otomatis

---

### Issue 4: "IPsec tunnel not established"

**Note:** IPsec tunnel **TIDAK** mempengaruhi dashboard!

Dashboard berjalan di port 5000 lokal, tidak tergantung IPsec.

**Jika ingin fix IPsec:**
```bash
# Cek status
sudo ipsec statusall | grep ESTABLISHED

# Restart IPsec
sudo ipsec restart

# Cek log
tail -f results/n3iwf_client.log
tail -f results/callbox.log
```

---

## 📞 Quick Commands

```bash
# Cek dashboard running
ps aux | grep dashboard.py

# Cek port 5000
sudo netstat -tulpn | grep 5000

# Cek log
tail -f results/dashboard.log

# Test localhost
curl http://localhost:5000

# Test external
curl http://10.42.0.1:5000

# Restart dashboard
pkill -f dashboard.py
cd ~/thesis
PYTHONPATH=/home/ubuntu/thesis python3 main/real/dashboard.py > results/dashboard.log 2>&1 &

# Restart semua
sudo ./stop_all.sh
sudo ./start_all.sh
```

---

## ✅ Expected Behavior

### Saat Start (0-10 detik)
```
✅ Dashboard process running
✅ Port 5000 listening
✅ Dashboard log: "Running on http://10.42.0.1:5000"
⚠️  Network stats: "not available yet" (normal)
⏳ Waiting for Pico 2W data
```

### Setelah 10-30 detik
```
✅ Dashboard accessible: http://10.42.0.1:5000
✅ Network stats muncul
✅ pH & Temperature data muncul
✅ Grafik mulai terisi
✅ IPsec status: ESTABLISHED (atau UNKNOWN - tidak masalah)
```

---

## 🆘 Jika Masih Gagal

1. **Jalankan diagnose script:**
   ```bash
   ./diagnose_dashboard.sh
   ```

2. **Copy output dan share:**
   - Dashboard log: `cat results/dashboard.log`
   - Run_real log: `cat results/run_real.log`
   - Process list: `ps aux | grep python`
   - Port status: `sudo netstat -tulpn | grep 5000`

3. **Try manual start untuk lihat error:**
   ```bash
   cd ~/thesis
   export PYTHONPATH=/home/ubuntu/thesis
   python3 main/real/dashboard.py
   # Lihat error yang muncul di terminal
   ```

---

## 📝 Summary

**Dashboard tidak bisa diakses biasanya karena:**
1. ❌ Dashboard process crashed (cek log)
2. ❌ Python import error (install packages)
3. ❌ PYTHONPATH tidak set (set di start_all.sh)
4. ❌ Port 5000 sudah dipakai (kill process)

**IPsec tunnel tidak established:**
- ✅ **TIDAK** mempengaruhi dashboard
- Dashboard tetap bisa diakses
- Network stats akan show "UNKNOWN" (normal)

**Quick fix:**
```bash
sudo ./stop_all.sh
sudo ./start_all.sh
# Tunggu 10 detik
# Akses: http://10.42.0.1:5000
```
