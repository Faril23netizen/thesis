#!/bin/bash
################################################################################
# start_all.sh - Start Complete N3IWF + Edge AI System
################################################################################
# Jalankan semua service untuk deployment lengkap:
# - Callbox 5G Simulator
# - N3IWF Client (IPsec)
# - run_real.py (Main system)
# - Dashboard
#
# Usage:
#   chmod +x start_all.sh
#   ./start_all.sh
#
# Stop:
#   ./stop_all.sh
################################################################################

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
PIDS_FILE="$RESULTS_DIR/.pids"

# Set PYTHONPATH to include project root
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

mkdir -p "$RESULTS_DIR"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Starting Complete N3IWF + Edge AI System${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check if running as root for IPsec
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ This script must be run as root (for IPsec setup)${NC}"
    echo -e "${YELLOW}   Run: sudo ./start_all.sh${NC}"
    exit 1
fi

# Clean up old PIDs
rm -f "$PIDS_FILE"

################################################################################
# Step 1: Check Dependencies
################################################################################
echo -e "${YELLOW}[1/7] Checking dependencies...${NC}"

# Check strongSwan
if ! command -v ipsec &> /dev/null; then
    echo -e "${RED}❌ strongSwan not installed${NC}"
    echo -e "${YELLOW}   Installing: sudo apt install -y strongswan strongswan-pki${NC}"
    apt install -y strongswan strongswan-pki libcharon-extra-plugins
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not installed${NC}"
    exit 1
fi

# Check Python packages
python3 -c "import flask" 2>/dev/null || {
    echo -e "${YELLOW}   Installing Flask...${NC}"
    pip3 install flask
}

python3 -c "import numpy" 2>/dev/null || {
    echo -e "${YELLOW}   Installing NumPy...${NC}"
    pip3 install numpy
}

python3 -c "import matplotlib" 2>/dev/null || {
    echo -e "${YELLOW}   Installing Matplotlib...${NC}"
    pip3 install matplotlib
}

echo -e "${GREEN}✅ Dependencies OK${NC}"
echo ""

################################################################################
# Step 2: Enable IP Forwarding
################################################################################
echo -e "${YELLOW}[2/7] Enabling IP forwarding...${NC}"
sysctl -w net.ipv4.ip_forward=1 > /dev/null
sysctl -w net.ipv6.conf.all.forwarding=1 > /dev/null
echo -e "${GREEN}✅ IP forwarding enabled${NC}"
echo ""

################################################################################
# Step 3: Start Callbox Simulator
################################################################################
echo -e "${YELLOW}[3/7] Starting Callbox 5G Simulator...${NC}"
PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/callbox_simulator.py" > "$RESULTS_DIR/callbox.log" 2>&1 &
CALLBOX_PID=$!
echo "$CALLBOX_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ Callbox started (PID: $CALLBOX_PID)${NC}"
echo -e "${BLUE}   Log: $RESULTS_DIR/callbox.log${NC}"
sleep 3
echo ""

################################################################################
# Step 4: Setup IPsec (Callbox Side)
################################################################################
echo -e "${YELLOW}[4/7] Preparing IPsec config (Callbox side)...${NC}"

# Wait for callbox to create config files
for i in {1..10}; do
    if [ -f "/tmp/ipsec_callbox.conf" ]; then
        break
    fi
    sleep 1
done

if [ -f "/tmp/ipsec_callbox.conf" ]; then
    echo -e "${GREEN}✅ Callbox IPsec config created${NC}"
    echo -e "${BLUE}   Config will be merged by N3IWF client${NC}"
else
    echo -e "${YELLOW}⚠️  Callbox IPsec config not found${NC}"
    echo -e "${YELLOW}   N3IWF will use standalone config${NC}"
fi
sleep 1
echo ""

################################################################################
# Step 5: Start N3IWF Client
################################################################################
echo -e "${YELLOW}[5/7] Starting N3IWF Client...${NC}"
PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/n3iwf_client.py" > "$RESULTS_DIR/n3iwf_client.log" 2>&1 &
N3IWF_PID=$!
echo "$N3IWF_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ N3IWF Client started (PID: $N3IWF_PID)${NC}"
echo -e "${BLUE}   Log: $RESULTS_DIR/n3iwf_client.log${NC}"
sleep 5
echo ""

################################################################################
# Step 6: Verify IPsec Tunnel
################################################################################
echo -e "${YELLOW}[6/7] Verifying IPsec tunnel...${NC}"

# Wait up to 30 seconds for tunnel to establish
TUNNEL_ESTABLISHED=false
for i in {1..30}; do
    if ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
        TUNNEL_ESTABLISHED=true
        break
    fi
    sleep 1
done

if [ "$TUNNEL_ESTABLISHED" = true ]; then
    echo -e "${GREEN}✅ IPsec tunnel ESTABLISHED${NC}"
    
    # Test connectivity
    if ping -c 2 -W 2 192.168.100.1 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Connectivity OK (ping successful)${NC}"
    else
        echo -e "${YELLOW}⚠️  Ping failed, but tunnel is up${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  IPsec tunnel not established after 30s${NC}"
    echo -e "${YELLOW}   This is OK - system will continue without IPsec${NC}"
    echo -e "${YELLOW}   To debug: ./diagnose_ipsec.sh${NC}"
    echo -e "${YELLOW}   To fix later: sudo ipsec restart${NC}"
fi
echo ""

################################################################################
# Step 7: Start Main System
################################################################################
echo -e "${YELLOW}[7/7] Starting main system...${NC}"

# Get real user (not root)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo ~$REAL_USER)

# Start run_real.py as real user
sudo -u "$REAL_USER" PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/main/real/run_real.py" > "$RESULTS_DIR/run_real.log" 2>&1 &
RUNREAL_PID=$!
echo "$RUNREAL_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ run_real.py started (PID: $RUNREAL_PID)${NC}"
echo -e "${BLUE}   Log: $RESULTS_DIR/run_real.log${NC}"
sleep 2

# Start dashboard as real user
sudo -u "$REAL_USER" PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/main/real/dashboard.py" > "$RESULTS_DIR/dashboard.log" 2>&1 &
DASHBOARD_PID=$!
echo "$DASHBOARD_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ Dashboard started (PID: $DASHBOARD_PID)${NC}"
echo -e "${BLUE}   Log: $RESULTS_DIR/dashboard.log${NC}"
echo ""

################################################################################
# Summary
################################################################################
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ ALL SERVICES STARTED SUCCESSFULLY!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Running Services:${NC}"
echo -e "  1. Callbox Simulator    (PID: $CALLBOX_PID)"
echo -e "  2. N3IWF Client         (PID: $N3IWF_PID)"
echo -e "  3. run_real.py          (PID: $RUNREAL_PID)"
echo -e "  4. Dashboard            (PID: $DASHBOARD_PID)"
echo ""
echo -e "${YELLOW}Access Points:${NC}"
echo -e "  Dashboard:  ${GREEN}http://$(hostname -I | awk '{print $1}'):5000${NC}"
echo -e "              ${BLUE}(Usually: http://10.42.0.1:5000 via USB tethering)${NC}"
echo -e "  TCP Port:   ${GREEN}5005${NC} (Pico 2W)"
echo ""
echo -e "${YELLOW}Logs:${NC}"
echo -e "  Callbox:    tail -f $RESULTS_DIR/callbox.log"
echo -e "  N3IWF:      tail -f $RESULTS_DIR/n3iwf_client.log"
echo -e "  Main:       tail -f $RESULTS_DIR/run_real.log"
echo -e "  Dashboard:  tail -f $RESULTS_DIR/dashboard.log"
echo ""
echo -e "${YELLOW}Monitor:${NC}"
echo -e "  IPsec:      sudo ipsec statusall | grep ESTABLISHED"
echo -e "  Data:       tail -f results/hasil_real/comparison.csv"
echo ""
echo -e "${YELLOW}Stop All:${NC}"
echo -e "  Run:        ${GREEN}./stop_all.sh${NC}"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}System is now running. Press Ctrl+C to stop monitoring.${NC}"
echo -e "${YELLOW}To stop all services, run: ./stop_all.sh${NC}"
echo ""

# Monitor logs
echo -e "${BLUE}Monitoring run_real.py log (Ctrl+C to exit monitoring):${NC}"
tail -f "$RESULTS_DIR/run_real.log"
