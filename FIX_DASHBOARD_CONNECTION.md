# 🔧 Fix Dashboard Connection Issue

## Problem
Dashboard UI muncul tapi stuck di "Connecting..." dan tidak load data.

## Root Cause
Browser tidak bisa fetch API endpoints karena CORS (Cross-Origin Resource Sharing) issue.

## Solution Applied
- ✅ Added CORS headers to Flask app
- ✅ Added API call logging for debugging
- ✅ Added test script for API endpoints

---

## 🚀 Update & Restart (di RPi5)

```bash
# 1. Stop sistem
cd ~/thesis
sudo ./stop_all.sh

# 2. Pull update terbaru
git pull origin master

# 3. Start ulang
sudo ./start_all.sh

# 4. Tunggu 10 detik, lalu akses
# Browser: http://10.42.0.1:5000
```

---

## 🧪 Test API Endpoints

Setelah start, test API endpoints:

```bash
cd ~/thesis
chmod +x test_dashboard_api.sh
./test_dashboard_api.sh
```

**Expected output:**
```json
1. Testing /api/state from localhost:
{
  "pH": 7.731,
  "T": 24.25,
  "action": "LOW",
  "phase": "Rule-Based",
  ...
}

2. Testing /api/network from localhost:
{
  "ipsec_status": "DOWN",
  "avg_latency_ms": 0,
  ...
}
```

Jika API test berhasil tapi browser masih stuck, coba:
1. **Hard refresh browser**: `Ctrl+Shift+R` atau `Cmd+Shift+R`
2. **Clear browser cache**
3. **Incognito/Private mode**
4. **Browser lain** (Chrome, Firefox, Edge)

---

## 🔍 Debug Dashboard

Jika masih stuck, cek log dashboard:

```bash
# Monitor dashboard log real-time
tail -f results/dashboard.log

# Cari API calls
grep "\[API\]" results/dashboard.log
```

**Expected log saat browser akses:**
```
[API] /api/state called from 10.42.0.1
[API] Returning state: pH=7.731, T=24.25
[API] /api/network called from 10.42.0.1
```

**Jika TIDAK ada log `[API]`:**
- Browser tidak bisa reach API endpoints
- Cek firewall atau network

---

## 📊 Verify Dashboard Status

```bash
# 1. Cek dashboard running
ps aux | grep dashboard.py

# 2. Cek port 5000
sudo netstat -tulpn | grep 5000

# 3. Test localhost
curl http://localhost:5000/api/state

# 4. Test dari IP hotspot
curl http://10.42.0.1:5000/api/state

# 5. Cek dashboard log
tail -n 50 results/dashboard.log
```

---

## 🎯 What Changed

### Before (Broken)
```python
# No CORS headers
app = Flask(__name__)

@app.route('/api/state')
def get_state():
    return jsonify(state)
```

**Result:** Browser blocks API calls due to CORS policy

### After (Fixed)
```python
# CORS enabled
app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@app.route('/api/state')
def get_state():
    print(f"[API] /api/state called")  # Logging
    return jsonify(state)
```

**Result:** Browser can fetch API, dashboard loads data

---

## ✅ Expected Behavior After Fix

### Dashboard UI
- ✅ System Status: **Online** (green)
- ✅ IPsec Tunnel: **DOWN** or **UNKNOWN** (orange) - normal jika IPsec belum established
- ✅ Pico 2W: **Connected** (green)
- ✅ pH & Temperature: **Real values** (7.731, 24.25°C)
- ✅ Charts: **Updating** every 2 seconds
- ✅ Network stats: **Real values** or "not available yet"

### Dashboard Log
```
[API] /api/state called from 10.42.0.1
[API] Returning state: pH=7.731, T=24.25
[API] /api/network called from 10.42.0.1
10.42.0.1 - - [18/May/2026 00:30:15] "GET /api/state HTTP/1.1" 200 -
10.42.0.1 - - [18/May/2026 00:30:15] "GET /api/network HTTP/1.1" 200 -
```

---

## 🆘 If Still Not Working

### Option 1: Manual Dashboard Restart

```bash
# Kill dashboard
pkill -f dashboard.py

# Start manually to see errors
cd ~/thesis
export PYTHONPATH=/home/ubuntu/thesis
python3 main/real/dashboard.py

# Watch for errors in terminal
```

### Option 2: Check Browser Console

1. Open browser: `http://10.42.0.1:5000`
2. Press `F12` (Developer Tools)
3. Go to **Console** tab
4. Look for errors (red text)

**Common errors:**
- `Failed to fetch` → Network issue
- `CORS policy` → CORS not working (should be fixed now)
- `net::ERR_CONNECTION_REFUSED` → Dashboard not running

### Option 3: Try Different Browser

- Chrome
- Firefox
- Edge
- Safari (if on Mac)

---

## 📝 Summary

**Problem:** Dashboard stuck at "Connecting..."

**Cause:** CORS blocking API calls from browser

**Fix:** Added CORS headers to Flask app

**Action Required:**
1. `git pull origin master`
2. `sudo ./stop_all.sh`
3. `sudo ./start_all.sh`
4. Wait 10 seconds
5. Access: `http://10.42.0.1:5000`
6. Hard refresh browser: `Ctrl+Shift+R`

**Dashboard should now load data properly!** 🎉
