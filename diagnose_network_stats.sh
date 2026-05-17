#!/bin/bash
################################################################################
# diagnose_network_stats.sh - Diagnose Network Stats Issues
################################################################################

echo "═══════════════════════════════════════════════════════════════════"
echo "  🔍 Network Stats Diagnostics"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}[1/12] Checking results/network directory...${NC}"
if [ -d "results/network" ]; then
    echo -e "${GREEN}✅ Directory exists${NC}"
    ls -la results/network/
else
    echo -e "${RED}❌ Directory NOT found${NC}"
    echo -e "${YELLOW}   Creating directory...${NC}"
    mkdir -p results/network
fi
echo ""

echo -e "${YELLOW}[2/12] Checking callbox_stats.json...${NC}"
if [ -f "results/network/callbox_stats.json" ]; then
    echo -e "${GREEN}✅ File exists${NC}"
    echo -e "${BLUE}File info:${NC}"
    ls -lh results/network/callbox_stats.json
    echo ""
    echo -e "${BLUE}Content:${NC}"
    cat results/network/callbox_stats.json | python3 -m json.tool 2>/dev/null || cat results/network/callbox_stats.json
else
    echo -e "${RED}❌ File NOT found${NC}"
    echo -e "${YELLOW}   Callbox simulator should create this file${NC}"
fi
echo ""

echo -e "${YELLOW}[3/12] Checking callbox simulator process...${NC}"
if ps aux | grep -v grep | grep "callbox_simulator.py" > /dev/null; then
    echo -e "${GREEN}✅ Callbox simulator running${NC}"
    ps aux | grep -v grep | grep "callbox_simulator.py"
else
    echo -e "${RED}❌ Callbox simulator NOT running${NC}"
    echo -e "${YELLOW}   Start with: sudo ./start_all.sh${NC}"
fi
echo ""

echo -e "${YELLOW}[4/12] Checking callbox log...${NC}"
if [ -f "results/callbox.log" ]; then
    echo -e "${GREEN}✅ Callbox log exists${NC}"
    echo -e "${BLUE}Last 30 lines:${NC}"
    tail -n 30 results/callbox.log
else
    echo -e "${RED}❌ Callbox log NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[5/12] Checking for stats saving in log...${NC}"
if [ -f "results/callbox.log" ]; then
    if grep -q "Stats saved" results/callbox.log; then
        echo -e "${GREEN}✅ Stats saving detected in log${NC}"
        echo -e "${BLUE}Recent stats saves:${NC}"
        grep "Stats saved" results/callbox.log | tail -n 5
    else
        echo -e "${RED}❌ No 'Stats saved' messages in log${NC}"
        echo -e "${YELLOW}   Callbox may not be saving stats${NC}"
    fi
else
    echo -e "${RED}❌ Cannot check log (file not found)${NC}"
fi
echo ""

echo -e "${YELLOW}[6/12] Checking for errors in callbox log...${NC}"
if [ -f "results/callbox.log" ]; then
    if grep -i "error" results/callbox.log > /dev/null; then
        echo -e "${RED}⚠️  Errors found in log:${NC}"
        grep -i "error" results/callbox.log | tail -n 10
    else
        echo -e "${GREEN}✅ No errors in log${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Cannot check (log not found)${NC}"
fi
echo ""

echo -e "${YELLOW}[7/12] Checking dashboard process...${NC}"
if ps aux | grep -v grep | grep "dashboard.py" > /dev/null; then
    echo -e "${GREEN}✅ Dashboard running${NC}"
    ps aux | grep -v grep | grep "dashboard.py"
else
    echo -e "${RED}❌ Dashboard NOT running${NC}"
fi
echo ""

echo -e "${YELLOW}[8/12] Checking dashboard log...${NC}"
if [ -f "results/dashboard.log" ]; then
    echo -e "${GREEN}✅ Dashboard log exists${NC}"
    echo -e "${BLUE}Last 20 lines:${NC}"
    tail -n 20 results/dashboard.log
else
    echo -e "${RED}❌ Dashboard log NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[9/12] Testing dashboard API endpoints...${NC}"
echo -e "${BLUE}Testing /api/network:${NC}"
if command -v curl &> /dev/null; then
    curl -s http://localhost:5000/api/network | python3 -m json.tool 2>/dev/null || echo "Failed to fetch"
else
    echo -e "${YELLOW}⚠️  curl not available${NC}"
fi
echo ""

echo -e "${YELLOW}[10/12] Checking file permissions...${NC}"
if [ -d "results/network" ]; then
    echo -e "${BLUE}Directory permissions:${NC}"
    ls -ld results/network/
    
    if [ -f "results/network/callbox_stats.json" ]; then
        echo -e "${BLUE}File permissions:${NC}"
        ls -l results/network/callbox_stats.json
    fi
else
    echo -e "${YELLOW}⚠️  Directory not found${NC}"
fi
echo ""

echo -e "${YELLOW}[11/12] Checking disk space...${NC}"
df -h results/
echo ""

echo -e "${YELLOW}[12/12] Testing manual stats file creation...${NC}"
echo -e "${BLUE}Attempting to create test file...${NC}"
TEST_FILE="results/network/test_write.json"
if echo '{"test": true}' > "$TEST_FILE" 2>/dev/null; then
    echo -e "${GREEN}✅ Can write to results/network/${NC}"
    rm -f "$TEST_FILE"
else
    echo -e "${RED}❌ Cannot write to results/network/${NC}"
    echo -e "${YELLOW}   Permission issue detected${NC}"
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════"
echo -e "${BLUE}  📋 Summary & Recommendations${NC}"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Summary
ISSUES=0

if [ ! -f "results/network/callbox_stats.json" ]; then
    echo -e "${RED}❌ CRITICAL: callbox_stats.json NOT found${NC}"
    ISSUES=$((ISSUES+1))
fi

if ! ps aux | grep -v grep | grep "callbox_simulator.py" > /dev/null; then
    echo -e "${RED}❌ CRITICAL: Callbox simulator NOT running${NC}"
    ISSUES=$((ISSUES+1))
fi

if [ -f "results/callbox.log" ] && ! grep -q "Stats saved" results/callbox.log; then
    echo -e "${YELLOW}⚠️  WARNING: No stats saving detected in log${NC}"
fi

if [ -f "results/callbox.log" ] && grep -i "error" results/callbox.log > /dev/null; then
    echo -e "${YELLOW}⚠️  WARNING: Errors found in callbox log${NC}"
fi

echo ""
if [ $ISSUES -eq 0 ]; then
    if [ -f "results/network/callbox_stats.json" ]; then
        echo -e "${GREEN}✅ No critical issues found${NC}"
        echo -e "${GREEN}   callbox_stats.json exists and should be working${NC}"
        echo ""
        echo -e "${BLUE}Current stats:${NC}"
        cat results/network/callbox_stats.json | python3 -m json.tool 2>/dev/null
    else
        echo -e "${YELLOW}⚠️  Stats file missing but no obvious errors${NC}"
        echo -e "${YELLOW}   System may need more time to create file${NC}"
    fi
else
    echo -e "${RED}❌ Found $ISSUES critical issue(s)${NC}"
    echo ""
    echo -e "${YELLOW}Recommended actions:${NC}"
    echo "1. Restart system: sudo ./stop_all.sh && sudo ./start_all.sh"
    echo "2. Wait 30 seconds for stats file to be created"
    echo "3. Check callbox log: tail -f results/callbox.log | grep 'Stats saved'"
    echo "4. Verify file created: cat results/network/callbox_stats.json"
    echo "5. If still failing, check permissions: ls -la results/network/"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo -e "${BLUE}  🔧 Quick Fix Commands${NC}"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "# Restart system"
echo "sudo ./stop_all.sh && sudo ./start_all.sh"
echo ""
echo "# Watch for stats file creation"
echo "watch -n 1 'ls -lh results/network/callbox_stats.json 2>/dev/null || echo \"File not created yet\"'"
echo ""
echo "# Monitor callbox log"
echo "tail -f results/callbox.log | grep --line-buffered 'Stats saved'"
echo ""
echo "# Test dashboard API"
echo "curl -s http://localhost:5000/api/network | python3 -m json.tool"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
