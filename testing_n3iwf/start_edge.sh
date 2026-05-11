#!/bin/bash

# start_edge.sh - Launch the Aquaculture Edge System
# Runs both the main FQL controller and the N3IWF dashboard in parallel

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

echo "========================================================="
echo " Starting Aquaculture Edge Services (N3IWF)"
echo "========================================================="

# --- N3IWF Amarisoft Mode ---
echo "[0] Initializing N3IWF IPsec Tunnel to Amarisoft (192.168.100.101)"
# Checking if strongSwan is installed
if command -v ipsec &> /dev/null; then
    echo "    strongSwan IPsec is installed. Ensuring tunnel is up..."
    # sudo ipsec restart  <-- Uncomment in Linux
    # sudo ipsec up aquaculture-n3iwf
    echo "    [i] Pastikan Anda telah meng-copy file konfigurasi:"
    echo "        sudo cp n3iwf_ipsec/ipsec.conf /etc/ipsec.conf"
    echo "        sudo cp n3iwf_ipsec/ipsec.secrets /etc/ipsec.secrets"
else
    echo "    [WARN] ipsec command not found. (Abaikan jika jalan di Windows)"
fi
echo ""

# Create results directory if it doesn't exist
mkdir -p results/hasil_real

# Start the dashboard in the foreground so you can see logs
echo "[1] Starting N3IWF Web Dashboard on http://localhost:5000"
echo "    (Press Ctrl+C to stop)"
echo ""
python3 n3iwf/dashboard.py
