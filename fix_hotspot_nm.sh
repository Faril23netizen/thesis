#!/bin/bash
# Quick Hotspot Fix for NetworkManager
# =====================================
# This script activates the N3IWF_AQUA hotspot using NetworkManager

set -e

echo "=========================================="
echo "  Quick Hotspot Fix (NetworkManager)"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run as root: sudo bash fix_hotspot_nm.sh"
    exit 1
fi

# Check if NetworkManager is running
if ! systemctl is-active --quiet NetworkManager; then
    echo "❌ NetworkManager is not running"
    echo "   Start it: sudo systemctl start NetworkManager"
    exit 1
fi

# Check if N3IWF_AQUA connection exists
if ! nmcli connection show N3IWF_AQUA &>/dev/null; then
    echo "⚠️  N3IWF_AQUA connection not found"
    echo "   Creating new hotspot..."
    echo ""
    
    # Create hotspot
    nmcli device wifi hotspot ifname wlan0 ssid N3IWF_AQUA password skripsi2026
    
    # Configure IP
    nmcli connection modify N3IWF_AQUA ipv4.addresses 10.42.0.1/24
    nmcli connection modify N3IWF_AQUA ipv4.method shared
    
    echo "✅ Hotspot created"
fi

# Activate hotspot
echo "🚀 Activating N3IWF_AQUA hotspot..."
nmcli connection up N3IWF_AQUA

sleep 2

# Verify
echo ""
echo "📊 Status:"
nmcli device status | grep wlan0
echo ""

# Check IP
IP=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
if [ "$IP" = "10.42.0.1" ]; then
    echo "✅ Hotspot active!"
    echo "   SSID: N3IWF_AQUA"
    echo "   IP:   10.42.0.1"
    echo ""
    echo "Next steps:"
    echo "  1. Run diagnostic: python3 diagnostic_network.py"
    echo "  2. Start server: python3 main/real/run_real.py"
else
    echo "⚠️  IP address is $IP (expected 10.42.0.1)"
    echo "   Fixing..."
    nmcli connection modify N3IWF_AQUA ipv4.addresses 10.42.0.1/24
    nmcli connection up N3IWF_AQUA
fi

