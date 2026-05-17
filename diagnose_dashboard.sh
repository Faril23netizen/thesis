#!/bin/bash
################################################################################
# diagnose_dashboard.sh - Diagnosa Dashboard Connection Issue
################################################################################

echo "═══════════════════════════════════════════════════════════════════"
echo "  🔍 Dashboard Diagnostics"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}[1/10] Checking if dashboard process is running...${NC}"
if ps aux | grep -v grep | grep "dashboard.py" > /dev/null; then
    echo -e "${GREEN}✅ Dashboard process is running${NC}"
    ps aux | grep -v grep | grep "dashboard.py"
else
    echo -e "${RED}❌ Dashboard process NOT running${NC}"
    echo -e "${YELLOW}   This is the problem! Dashboard crashed or didn't start.${NC}"
fi
echo ""

echo -e "${YELLOW}[2/10] Checking port 5000...${NC}"
if command -v netstat &> /dev/null; then
    if sudo netstat -tulpn | grep ":5000" > /dev/null; then
        echo -e "${GREEN}✅ Port 5000 is listening${NC}"
        sudo netstat -tulpn | grep ":5000"
    else
        echo -e "${RED}❌ Port 5000 is NOT listening${NC}"
        echo -e "${YELLOW}   Dashboard is not running or failed to bind to port 5000${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  netstat not available, trying ss...${NC}"
    if sudo ss -tulpn | grep ":5000" > /dev/null; then
        echo -e "${GREEN}✅ Port 5000 is listening${NC}"
        sudo ss -tulpn | grep ":5000"
    else
        echo -e "${RED}❌ Port 5000 is NOT listening${NC}"
    fi
fi
echo ""

echo -e "${YELLOW}[3/10] Checking dashboard log...${NC}"
if [ -f "results/dashboard.log" ]; then
    echo -e "${GREEN}✅ Dashboard log exists${NC}"
    echo -e "${BLUE}Last 20 lines:${NC}"
    tail -n 20 results/dashboard.log
else
    echo -e "${RED}❌ Dashboard log NOT found${NC}"
    echo -e "${YELLOW}   Dashboard never started or crashed immediately${NC}"
fi
echo ""

echo -e "${YELLOW}[4/10] Checking run_real.py process...${NC}"
if ps aux | grep -v grep | grep "run_real.py" > /dev/null; then
    echo -e "${GREEN}✅ run_real.py is running${NC}"
else
    echo -e "${RED}❌ run_real.py NOT running${NC}"
    echo -e "${YELLOW}   Main system is not running${NC}"
fi
echo ""

echo -e "${YELLOW}[5/10] Checking run_real.py log...${NC}"
if [ -f "results/run_real.log" ]; then
    echo -e "${GREEN}✅ run_real.log exists${NC}"
    echo -e "${BLUE}Last 20 lines:${NC}"
    tail -n 20 results/run_real.log
else
    echo -e "${RED}❌ run_real.log NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[6/10] Checking state.json...${NC}"
if [ -f "results/hasil_real/state.json" ]; then
    echo -e "${GREEN}✅ state.json exists${NC}"
    cat results/hasil_real/state.json
else
    echo -e "${RED}❌ state.json NOT found${NC}"
    echo -e "${YELLOW}   run_real.py hasn't created state file yet${NC}"
fi
echo ""

echo -e "${YELLOW}[7/10] Checking network stats...${NC}"
if [ -f "results/network/callbox_stats.json" ]; then
    echo -e "${GREEN}✅ callbox_stats.json exists${NC}"
    cat results/network/callbox_stats.json
else
    echo -e "${YELLOW}⚠️  callbox_stats.json NOT found${NC}"
    echo -e "${YELLOW}   This is OK - dashboard should handle this gracefully${NC}"
fi
echo ""

echo -e "${YELLOW}[8/10] Testing localhost connection...${NC}"
if command -v curl &> /dev/null; then
    echo -e "${BLUE}Testing: curl http://localhost:5000${NC}"
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5000 | grep -q "200"; then
        echo -e "${GREEN}✅ Dashboard responds on localhost${NC}"
    else
        echo -e "${RED}❌ Dashboard NOT responding on localhost${NC}"
        echo -e "${YELLOW}   HTTP Status: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  curl not available${NC}"
fi
echo ""

echo -e "${YELLOW}[9/10] Checking Python imports...${NC}"
if python3 -c "import flask, numpy, matplotlib; print('✅ All imports OK')" 2>/dev/null; then
    echo -e "${GREEN}✅ Python packages installed${NC}"
else
    echo -e "${RED}❌ Missing Python packages${NC}"
    echo -e "${YELLOW}   Install: pip3 install flask numpy matplotlib${NC}"
fi
echo ""

echo -e "${YELLOW}[10/10] Checking PYTHONPATH...${NC}"
echo -e "${BLUE}PYTHONPATH: $PYTHONPATH${NC}"
if [ -z "$PYTHONPATH" ]; then
    echo -e "${YELLOW}⚠️  PYTHONPATH not set${NC}"
    echo -e "${YELLOW}   This might cause import errors${NC}"
else
    echo -e "${GREEN}✅ PYTHONPATH is set${NC}"
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════"
echo -e "${BLUE}  📋 Summary${NC}"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Summary
ISSUES=0

if ! ps aux | grep -v grep | grep "dashboard.py" > /dev/null; then
    echo -e "${RED}❌ CRITICAL: Dashboard process not running${NC}"
    ISSUES=$((ISSUES+1))
fi

if ! sudo netstat -tulpn 2>/dev/null | grep ":5000" > /dev/null && ! sudo ss -tulpn 2>/dev/null | grep ":5000" > /dev/null; then
    echo -e "${RED}❌ CRITICAL: Port 5000 not listening${NC}"
    ISSUES=$((ISSUES+1))
fi

if [ ! -f "results/dashboard.log" ]; then
    echo -e "${RED}❌ CRITICAL: Dashboard log missing${NC}"
    ISSUES=$((ISSUES+1))
fi

if ! ps aux | grep -v grep | grep "run_real.py" > /dev/null; then
    echo -e "${YELLOW}⚠️  WARNING: run_real.py not running${NC}"
fi

if [ ! -f "results/hasil_real/state.json" ]; then
    echo -e "${YELLOW}⚠️  WARNING: state.json missing (data not available yet)${NC}"
fi

echo ""
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ No critical issues found${NC}"
    echo -e "${BLUE}Dashboard should be accessible at: http://10.42.0.1:5000${NC}"
else
    echo -e "${RED}❌ Found $ISSUES critical issue(s)${NC}"
    echo ""
    echo -e "${YELLOW}Recommended actions:${NC}"
    echo "1. Check dashboard log: tail -f results/dashboard.log"
    echo "2. Try manual start: python3 main/real/dashboard.py"
    echo "3. Check for errors in run_real.log"
    echo "4. Restart system: sudo ./stop_all.sh && sudo ./start_all.sh"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
