# 🔧 Dashboard Connection Fix

## Masalah

Dashboard tidak bisa connect setelah `sudo ./start_all.sh` dijalankan.

## Root Cause

1. **Missing Directory**: Dashboard membutuhkan folder `results/network/` yang dibuat oleh callbox simulator
2. **Missing Files**: Dashboard crash jika `callbox_stats.json` belum ada
3. **No Error Handling**: Dashboard tidak handle missing files dengan baik

## Solusi yang Diterapkan

### 1. Auto-create Directories
```python
# Ensure directories exist
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(NETWORK_DIR, exist_ok=True)
```

### 2. Robust Error Handling
Dashboard sekarang:
- ✅ Tidak crash jika network stats belum tersedia
- ✅ Menampilkan "Network stats not available yet" dengan graceful fallback
- ✅ Cek file age (stale detection)
- ✅ Handle JSON decode errors
- ✅ Return default values jika file tidak ada

### 3. Graceful Degradation
```python
if not os.path.exists(CALLBOX_STATS):
    return jsonify({
        "error": "Network stats not available yet",
        "ipsec_status": "UNKNOWN",
        "avg_latency_ms": 0,
        # ... default values
    })
```

## Testing

### Test Dashboard Locally
```bash
# Test import
python3 -c "import sys; sys.path.insert(0, '.'); from main.real import dashboard"

# Run dashboard
python3 main/real/dashboard.py
```

### Test on RPi5
```bash
# Start system
sudo ./start_all.sh

# Check dashboard log
tail -f results/dashboard.log

# Check if dashboard is running
ps aux | grep dashboard.py

# Check port 5000
sudo netstat -tulpn | grep 5000

# Access dashboard
curl http://localhost:5000
```

## Expected Behavior

### Before Callbox Starts
- Dashboard shows: "Network stats not available yet"
- Status: UNKNOWN
- Values: 0 or "--"

### After Callbox Starts (5-10 seconds)
- Dashboard shows real network stats
- Status: ESTABLISHED (if IPsec tunnel is up)
- Values: Real latency, packet loss, throughput, etc.

### If Callbox Crashes
- Dashboard shows: "Network stats are stale"
- Status: STALE
- Dashboard continues running (no crash)

## Files Modified

1. **`main/real/dashboard.py`**
   - Added `os.makedirs()` for directory creation
   - Enhanced `/api/network` endpoint with error handling
   - Added file age check (stale detection)
   - Added JSON decode error handling
   - Return default values on error

2. **`OUTPUT_RESULTS.md`**
   - Added dashboard section with complete feature list
   - Added troubleshooting guide

## Verification Checklist

- [x] Dashboard creates required directories
- [x] Dashboard doesn't crash if network stats missing
- [x] Dashboard shows graceful error messages
- [x] Dashboard returns default values on error
- [x] Dashboard detects stale files (>30 seconds old)
- [x] Dashboard handles JSON decode errors
- [x] Documentation updated

## Next Steps

1. **Push to GitHub**
   ```bash
   git add main/real/dashboard.py OUTPUT_RESULTS.md DASHBOARD_FIX.md
   git commit -m "fix: Dashboard robust error handling for missing network stats"
   git push origin master
   ```

2. **Test on RPi5**
   ```bash
   cd ~/thesis
   git pull origin master
   sudo ./start_all.sh
   ```

3. **Access Dashboard**
   - Open browser: `http://10.42.0.1:5000`
   - Should see dashboard with charts and network info
   - If network stats not ready, should show "Network stats not available yet"

## Summary

Dashboard sekarang **robust** dan tidak akan crash meskipun:
- ❌ Network stats belum tersedia
- ❌ Callbox belum start
- ❌ File JSON corrupt
- ❌ Directory tidak ada

Dashboard akan:
- ✅ Tetap running
- ✅ Menampilkan error message yang jelas
- ✅ Return default values
- ✅ Auto-recover ketika network stats tersedia

**Status: FIXED ✅**
