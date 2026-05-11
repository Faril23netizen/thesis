#!/bin/bash
# =============================================================
# start_testing.sh - Aquaculture N3IWF Testing Launcher
# Jalankan sekali untuk memulai seluruh sistem pengujian
# Usage: bash start_testing.sh
# =============================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo ""
echo "========================================================="
echo "  Aquaculture N3IWF Testing System"
echo "========================================================="
echo ""

# Step 1: IPsec Tunnel
echo "[1/3] Mengaktifkan IPsec Tunnel ke Callbox (192.168.100.101)..."
if command -v ipsec &> /dev/null; then
    sudo ipsec rereadsecrets 2>/dev/null
    sudo ipsec up aquaculture-n3iwf 2>/dev/null | grep -E "established|failed|ESTABLISHED"
    STATUS=$(sudo ipsec statusall 2>/dev/null | grep "ESTABLISHED" | wc -l)
    if [ "$STATUS" -gt "0" ]; then
        echo "    ✅ IPsec Tunnel: ESTABLISHED"
    else
        echo "    ⚠️  IPsec Tunnel belum terhubung. Coba jalankan manual:"
        echo "       sudo ipsec up aquaculture-n3iwf"
    fi
else
    echo "    ⚠️  ipsec tidak ditemukan. Install dulu: sudo apt install strongswan"
fi
echo ""

# Step 2: Install Python deps
echo "[2/3] Memastikan dependensi Python tersedia..."
pip3 install flask flask-cors --quiet 2>/dev/null
echo "    ✅ Flask siap"
echo ""

# Step 3: Start Server + Dashboard
echo "[3/3] Memulai TCP Server + Dashboard..."
echo ""

# Get IP
RPI_IP=$(hostname -I | awk '{print $1}')
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  Dashboard  : http://${RPI_IP}:5000          "
echo "  │  TCP Port   : 5005 (menunggu Pico 2W)        "
echo "  │                                               "
echo "  │  Buka dashboard di browser laptop/HP Anda!   "
echo "  └─────────────────────────────────────────────┘"
echo ""
echo "  (Tekan Ctrl+C untuk berhenti)"
echo ""

python3 "$DIR/server.py"
