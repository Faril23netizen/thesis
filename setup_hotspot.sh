#!/bin/bash
# Setup WiFi Hotspot for Pico WH Connection
# ==========================================
# This script configures RPi5 as WiFi Access Point
# SSID: N3IWF_AQUA
# Password: skripsi2026
# IP: 10.42.0.1

set -e

echo "=========================================="
echo "  WiFi Hotspot Setup for Pico WH"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run as root: sudo bash setup_hotspot.sh"
    exit 1
fi

echo "📦 Installing required packages..."
apt-get update -qq
apt-get install -y hostapd dnsmasq iptables

echo ""
echo "🔧 Configuring network interface..."

# Stop services
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

# Configure static IP for wlan0
cat > /etc/dhcpcd.conf.d/wlan0.conf <<EOF
interface wlan0
    static ip_address=10.42.0.1/24
    nohook wpa_supplicant
EOF

# Restart dhcpcd
systemctl restart dhcpcd
sleep 2

echo ""
echo "📡 Configuring hostapd (WiFi AP)..."

# Backup existing config
if [ -f /etc/hostapd/hostapd.conf ]; then
    cp /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.backup
fi

# Create hostapd config
cat > /etc/hostapd/hostapd.conf <<EOF
# WiFi interface
interface=wlan0

# Driver
driver=nl80211

# SSID
ssid=N3IWF_AQUA

# WiFi mode (g = 2.4GHz)
hw_mode=g

# Channel
channel=7

# Enable WPA2
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=skripsi2026
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# Set hostapd config path
cat > /etc/default/hostapd <<EOF
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOF

echo ""
echo "🌐 Configuring dnsmasq (DHCP server)..."

# Backup existing config
if [ -f /etc/dnsmasq.conf ]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.backup
fi

# Create dnsmasq config
cat > /etc/dnsmasq.conf <<EOF
# Interface to listen on
interface=wlan0

# DHCP range
dhcp-range=10.42.0.2,10.42.0.20,255.255.255.0,24h

# DNS server
dhcp-option=6,10.42.0.1

# Domain
domain=local

# Don't read /etc/resolv.conf
no-resolv

# Use Google DNS
server=8.8.8.8
server=8.8.4.4
EOF

echo ""
echo "🔥 Configuring firewall..."

# Enable IP forwarding
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-ip-forward.conf
sysctl -p /etc/sysctl.d/99-ip-forward.conf

# Allow port 5000
ufw allow 5000/tcp 2>/dev/null || true

echo ""
echo "🚀 Starting services..."

# Unmask and enable services
systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

# Start services
systemctl start hostapd
systemctl start dnsmasq

# Wait a bit
sleep 3

echo ""
echo "✅ Hotspot setup complete!"
echo ""
echo "=========================================="
echo "  Hotspot Configuration"
echo "=========================================="
echo "  SSID:     N3IWF_AQUA"
echo "  Password: skripsi2026"
echo "  IP:       10.42.0.1"
echo "  DHCP:     10.42.0.2 - 10.42.0.20"
echo "=========================================="
echo ""

# Check status
echo "📊 Service Status:"
echo ""
systemctl status hostapd --no-pager -l | head -5
echo ""
systemctl status dnsmasq --no-pager -l | head -5
echo ""

echo "✅ Setup complete! Pico WH can now connect to N3IWF_AQUA"
echo ""
echo "Next steps:"
echo "  1. Flash Pico WH with updated firmware"
echo "  2. Run diagnostic: python3 diagnostic_network.py"
echo "  3. Start server: python3 main/real/run_real.py"
echo ""
