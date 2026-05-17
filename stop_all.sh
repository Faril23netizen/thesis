#!/bin/bash
################################################################################
# stop_all.sh - Stop Complete N3IWF + Edge AI System
################################################################################
# Menghentikan semua service yang dijalankan oleh start_all.sh:
# - Dashboard
# - run_real.py
# - N3IWF Client
# - Callbox Simulator
# - IPsec Tunnel
#
# Usage:
#   chmod +x stop_all.sh
#   sudo ./stop_all.sh
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

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Stopping Complete N3IWF + Edge AI System${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ This script must be run as root${NC}"
    echo -e "${YELLOW}   Run: sudo ./stop_all.sh${NC}"
    exit 1
fi

################################################################################
# Step 1: Stop Services from PID File
################################################################################
echo -e "${YELLOW}[1/5] Stopping services from PID file...${NC}"

if [ -f "$PIDS_FILE" ]; then
    while IFS= read -r pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            # Get process name
            PROC_NAME=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
            echo -e "  Stopping $PROC_NAME (PID: $pid)..."
            kill -TERM "$pid" 2>/dev/null || true
            
            # Wait for graceful shutdown (max 5 seconds)
            for i in {1..10}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    echo -e "  ${GREEN}✅ Stopped${NC}"
                    break
                fi
                sleep 0.5
            done
            
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "  ${YELLOW}⚠️  Force killing...${NC}"
                kill -9 "$pid" 2>/dev/null || true
                sleep 1
            fi
        fi
    done < "$PIDS_FILE"
    
    rm -f "$PIDS_FILE"
    echo -e "${GREEN}✅ Services stopped${NC}"
else
    echo -e "${YELLOW}⚠️  No PID file found${NC}"
fi
echo ""

################################################################################
# Step 2: Stop Python Processes
################################################################################
echo -e "${YELLOW}[2/5] Stopping remaining Python processes...${NC}"

# Stop specific Python scripts
SCRIPTS=(
    "callbox_simulator.py"
    "n3iwf_client.py"
    "run_real.py"
    "dashboard.py"
    "server.py"
)

for script in "${SCRIPTS[@]}"; do
    PIDS=$(pgrep -f "$script" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo -e "  Stopping $script..."
        pkill -TERM -f "$script" 2>/dev/null || true
        sleep 1
        
        # Force kill if still running
        if pgrep -f "$script" > /dev/null 2>&1; then
            pkill -9 -f "$script" 2>/dev/null || true
        fi
        echo -e "  ${GREEN}✅ Stopped${NC}"
    fi
done

echo -e "${GREEN}✅ Python processes stopped${NC}"
echo ""

################################################################################
# Step 3: Stop IPsec Tunnel
################################################################################
echo -e "${YELLOW}[3/5] Stopping IPsec tunnel...${NC}"

if command -v ipsec &> /dev/null; then
    # Check if IPsec is running
    if ipsec status > /dev/null 2>&1; then
        echo -e "  Stopping IPsec service..."
        ipsec stop > /dev/null 2>&1 || true
        sleep 2
        echo -e "${GREEN}✅ IPsec stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  IPsec not running${NC}"
    fi
    
    # Clean up IPsec PID files
    rm -f /var/run/charon.pid 2>/dev/null || true
    rm -f /var/run/starter.charon.pid 2>/dev/null || true
else
    echo -e "${YELLOW}⚠️  strongSwan not installed${NC}"
fi
echo ""

################################################################################
# Step 4: Clean Up Temporary Files
################################################################################
echo -e "${YELLOW}[4/5] Cleaning up temporary files...${NC}"

# Remove temporary IPsec configs
rm -f /tmp/ipsec_callbox.conf 2>/dev/null || true
rm -f /tmp/ipsec_callbox.secrets 2>/dev/null || true
rm -f /tmp/ipsec_n3iwf.conf 2>/dev/null || true
rm -f /tmp/ipsec_n3iwf.secrets 2>/dev/null || true

echo -e "${GREEN}✅ Temporary files cleaned${NC}"
echo ""

################################################################################
# Step 5: Verify All Stopped
################################################################################
echo -e "${YELLOW}[5/5] Verifying all services stopped...${NC}"

STILL_RUNNING=0

# Check Python processes
for script in "${SCRIPTS[@]}"; do
    if pgrep -f "$script" > /dev/null 2>&1; then
        echo -e "${RED}❌ Still running: $script${NC}"
        STILL_RUNNING=1
    fi
done

# Check IPsec
if command -v ipsec &> /dev/null; then
    if ipsec status > /dev/null 2>&1; then
        echo -e "${RED}❌ IPsec still running${NC}"
        STILL_RUNNING=1
    fi
fi

if [ $STILL_RUNNING -eq 0 ]; then
    echo -e "${GREEN}✅ All services stopped successfully${NC}"
else
    echo -e "${YELLOW}⚠️  Some services may still be running${NC}"
    echo -e "${YELLOW}   Check manually: ps aux | grep python${NC}"
fi
echo ""

################################################################################
# Summary
################################################################################
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ SYSTEM STOPPED${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Logs preserved in:${NC}"
echo -e "  $RESULTS_DIR/callbox.log"
echo -e "  $RESULTS_DIR/n3iwf_client.log"
echo -e "  $RESULTS_DIR/run_real.log"
echo -e "  $RESULTS_DIR/dashboard.log"
echo ""
echo -e "${YELLOW}Data preserved in:${NC}"
echo -e "  results/hasil_real/comparison.csv"
echo -e "  results/network/callbox_stats.json"
echo -e "  results/network/n3iwf_status.json"
echo ""
echo -e "${YELLOW}To restart:${NC}"
echo -e "  ${GREEN}sudo ./start_all.sh${NC}"
echo ""
echo -e "${YELLOW}To analyze results:${NC}"
echo -e "  ${GREEN}python3 analyze_all.py${NC}"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
