#!/bin/bash
################################################################################
# quick_restart.sh - Quick Clean Restart After Improper Shutdown
################################################################################
# Script ini membersihkan proses orphan dan restart sistem dengan bersih
# setelah RPi5 dimatikan tanpa menjalankan stop_all.sh
#
# Usage:
#   chmod +x quick_restart.sh
#   sudo ./quick_restart.sh
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Quick Clean Restart${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ This script must be run as root${NC}"
    echo -e "${YELLOW}   Run: sudo ./quick_restart.sh${NC}"
    exit 1
fi

################################################################################
# Step 1: Make Scripts Executable
################################################################################
echo -e "${YELLOW}[1/5] Making scripts executable...${NC}"
chmod +x start_all.sh stop_all.sh diagnose_ipsec.sh diagnose_network_stats.sh
echo -e "${GREEN}✅ Scripts are now executable${NC}"
echo ""

################################################################################
# Step 2: Clean Up Orphan Processes
################################################################################
echo -e "${YELLOW}[2/5] Cleaning up orphan processes...${NC}"

ORPHANS_FOUND=0

# Check for thesis-related Python processes
if pgrep -f "callbox_simulator.py" > /dev/null 2>&1; then
    echo -e "  Killing callbox_simulator.py..."
    pkill -9 -f callbox_simulator.py 2>/dev/null || true
    ORPHANS_FOUND=1
fi

if pgrep -f "n3iwf_client.py" > /dev/null 2>&1; then
    echo -e "  Killing n3iwf_client.py..."
    pkill -9 -f n3iwf_client.py 2>/dev/null || true
    ORPHANS_FOUND=1
fi

if pgrep -f "run_real.py" > /dev/null 2>&1; then
    echo -e "  Killing run_real.py..."
    pkill -9 -f run_real.py 2>/dev/null || true
    ORPHANS_FOUND=1
fi

if pgrep -f "dashboard.py" > /dev/null 2>&1; then
    echo -e "  Killing dashboard.py..."
    pkill -9 -f dashboard.py 2>/dev/null || true
    ORPHANS_FOUND=1
fi

if [ $ORPHANS_FOUND -eq 1 ]; then
    echo -e "${GREEN}✅ Orphan processes cleaned${NC}"
    sleep 2
else
    echo -e "${GREEN}✅ No orphan processes found${NC}"
fi
echo ""

################################################################################
# Step 3: Stop IPsec
################################################################################
echo -e "${YELLOW}[3/5] Stopping IPsec...${NC}"

if command -v ipsec &> /dev/null; then
    if ipsec status > /dev/null 2>&1; then
        ipsec stop > /dev/null 2>&1 || true
        sleep 2
        echo -e "${GREEN}✅ IPsec stopped${NC}"
    else
        echo -e "${GREEN}✅ IPsec not running${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  strongSwan not installed${NC}"
fi
echo ""

################################################################################
# Step 4: Clean Up Stale Files
################################################################################
echo -e "${YELLOW}[4/5] Cleaning up stale files...${NC}"

# Remove PID file
if [ -f "results/.pids" ]; then
    rm -f results/.pids
    echo -e "  Removed stale PID file"
fi

# Remove IPsec PID files
rm -f /var/run/charon.pid 2>/dev/null || true
rm -f /var/run/starter.charon.pid 2>/dev/null || true

echo -e "${GREEN}✅ Stale files cleaned${NC}"
echo ""

################################################################################
# Step 5: Start System
################################################################################
echo -e "${YELLOW}[5/5] Starting system...${NC}"
echo ""

# Run start_all.sh
./start_all.sh

