#!/bin/bash

# start_edge.sh - Launch the Aquaculture Edge System
# Runs both the main FQL controller and the N3IWF dashboard in parallel

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

echo "========================================================="
echo " Starting Aquaculture Edge Services (N3IWF)"
echo "========================================================="

# --- Cek status IPsec tunnel ke Amarisoft N3IWF ---
echo "[0] Checking N3IWF IPsec tunnel (strongSwan)..."
if ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
    echo "    [OK] IPsec tunnel ke Amarisoft N3IWF: ESTABLISHED"
else
    echo "    [WARN] IPsec tunnel tidak aktif. Mencoba restart strongSwan..."
    sudo systemctl restart strongswan-starter 2>/dev/null || true
    sleep 3
    if ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
        echo "    [OK] IPsec tunnel berhasil dibuat."
    else
        echo "    [WARN] IPsec tunnel GAGAL. Pastikan Amarisoft N3IWF Callbox aktif."
        echo "           Sistem akan tetap berjalan dengan koneksi lokal saja."
    fi
fi
echo ""

# Create results directory if it doesn't exist
mkdir -p results/hasil_real

# Start the dashboard in the background
echo "[1] Starting N3IWF Web Dashboard on http://localhost:5000"
python3 n3iwf/dashboard.py > results/hasil_real/dashboard.log 2>&1 &
DASHBOARD_PID=$!

# Start the main controller
echo "[2] Starting Main Progressive Hybrid Controller (run_real.py)"
echo "    (Press Ctrl+C to stop both services)"
echo ""

# Run main controller in the foreground so the user sees the output
python3 -m main.real.run_real

# When the main controller stops (e.g. Ctrl+C), kill the dashboard
echo "Shutting down Edge Services..."
kill $DASHBOARD_PID
echo "Done."
