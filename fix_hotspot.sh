#!/bin/bash
# Quick Hotspot Fix Script
# =========================
# This script checks if hostapd is configured and starts it.
# If not configured, it runs the full setup.

set -e

echo "=========================================="
echo "  Quick Hotspot Fix"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run as root: sudo bash fix_hotspot.sh"
    exit 1
fi

# Check if hostapd config exists
if [ -f /etc/hostapd/hostapd.conf ]; then
    echo "✅ hostapd configuration found"
    echo ""
    
    # Check if it's configured for N3IWF_AQUA
    if grep -q "ssid=N3IWF_AQUA" /etc/hostapd/hostapd.conf; then
        echo "✅ Configuration is correct (SSID: N3IWF_AQUA)"
        echo ""
        echo "🚀 Starting hostapd and dnsmasq services..."
        
        # Unmask and enable services
        systemctl unmask hostapd 2>/dev/null || true
        systemctl enable hostapd 2>/dev/null || true
        systemctl enable dnsmasq 2>/dev/null || true
        
        # Start services
        systemctl start hostapd
        systemctl start dnsmasq
        
        sleep 2
        
        echo ""
        echo "📊 Service Status:"
        echo ""
        systemctl status hostapd --no-pager -l | head -5
        echo ""
        systemctl status dnsmasq --no-pager -l | head -5
        echo ""
        
        echo "✅ Hotspot is now active!"
        echo ""
        echo "Next steps:"
        echo "  1. Run diagnostic: python3 diagnostic_network.py"
        echo "  2. Start server: python3 main/real/run_real.py"
        echo ""
    else
        echo "⚠️  Configuration exists but SSID is different"
        echo "    Running full setup to reconfigure..."
        echo ""
        bash setup_hotspot.sh
    fi
else
    echo "⚠️  No hostapd configuration found"
    echo "    Running full setup..."
    echo ""
    bash setup_hotspot.sh
fi

