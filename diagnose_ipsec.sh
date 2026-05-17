#!/bin/bash
################################################################################
# diagnose_ipsec.sh - Diagnose IPsec Tunnel Issues
################################################################################

echo "═══════════════════════════════════════════════════════════════════"
echo "  🔍 IPsec Tunnel Diagnostics"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${YELLOW}[1/10] Checking strongSwan installation...${NC}"
if command -v ipsec &> /dev/null; then
    echo -e "${GREEN}✅ strongSwan installed${NC}"
    ipsec --version | head -n 1
else
    echo -e "${RED}❌ strongSwan NOT installed${NC}"
    echo -e "${YELLOW}   Install: sudo apt install strongswan strongswan-pki libcharon-extra-plugins${NC}"
fi
echo ""

echo -e "${YELLOW}[2/10] Checking IPsec service status...${NC}"
if sudo ipsec status &> /dev/null; then
    echo -e "${GREEN}✅ IPsec service running${NC}"
else
    echo -e "${RED}❌ IPsec service NOT running${NC}"
    echo -e "${YELLOW}   Start: sudo ipsec start${NC}"
fi
echo ""

echo -e "${YELLOW}[3/10] Checking IPsec config files...${NC}"
if [ -f "/etc/ipsec.conf" ]; then
    echo -e "${GREEN}✅ /etc/ipsec.conf exists${NC}"
    echo -e "${BLUE}Content:${NC}"
    cat /etc/ipsec.conf
else
    echo -e "${RED}❌ /etc/ipsec.conf NOT found${NC}"
fi
echo ""

if [ -f "/etc/ipsec.secrets" ]; then
    echo -e "${GREEN}✅ /etc/ipsec.secrets exists${NC}"
    echo -e "${BLUE}Permissions:${NC}"
    ls -l /etc/ipsec.secrets
else
    echo -e "${RED}❌ /etc/ipsec.secrets NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[4/10] Checking temp config files...${NC}"
if [ -f "/tmp/ipsec_callbox.conf" ]; then
    echo -e "${GREEN}✅ /tmp/ipsec_callbox.conf exists${NC}"
else
    echo -e "${YELLOW}⚠️  /tmp/ipsec_callbox.conf NOT found${NC}"
    echo -e "${YELLOW}   Callbox simulator should create this${NC}"
fi

if [ -f "/tmp/ipsec_callbox.secrets" ]; then
    echo -e "${GREEN}✅ /tmp/ipsec_callbox.secrets exists${NC}"
else
    echo -e "${YELLOW}⚠️  /tmp/ipsec_callbox.secrets NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[5/10] Checking IPsec tunnel status...${NC}"
sudo ipsec statusall 2>/dev/null | head -n 30
echo ""

if sudo ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
    echo -e "${GREEN}✅ IPsec tunnel ESTABLISHED${NC}"
else
    echo -e "${RED}❌ IPsec tunnel NOT established${NC}"
fi
echo ""

echo -e "${YELLOW}[6/10] Checking callbox process...${NC}"
if ps aux | grep -v grep | grep "callbox_simulator.py" > /dev/null; then
    echo -e "${GREEN}✅ Callbox simulator running${NC}"
    ps aux | grep -v grep | grep "callbox_simulator.py"
else
    echo -e "${RED}❌ Callbox simulator NOT running${NC}"
fi
echo ""

echo -e "${YELLOW}[7/10] Checking N3IWF client process...${NC}"
if ps aux | grep -v grep | grep "n3iwf_client.py" > /dev/null; then
    echo -e "${GREEN}✅ N3IWF client running${NC}"
    ps aux | grep -v grep | grep "n3iwf_client.py"
else
    echo -e "${RED}❌ N3IWF client NOT running${NC}"
fi
echo ""

echo -e "${YELLOW}[8/10] Checking callbox log...${NC}"
if [ -f "results/callbox.log" ]; then
    echo -e "${GREEN}✅ Callbox log exists${NC}"
    echo -e "${BLUE}Last 20 lines:${NC}"
    tail -n 20 results/callbox.log
else
    echo -e "${RED}❌ Callbox log NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[9/10] Checking N3IWF client log...${NC}"
if [ -f "results/n3iwf_client.log" ]; then
    echo -e "${GREEN}✅ N3IWF client log exists${NC}"
    echo -e "${BLUE}Last 20 lines:${NC}"
    tail -n 20 results/n3iwf_client.log
else
    echo -e "${RED}❌ N3IWF client log NOT found${NC}"
fi
echo ""

echo -e "${YELLOW}[10/10] Checking network connectivity...${NC}"
echo -e "${BLUE}Testing ping to tunnel IPs:${NC}"

if ping -c 2 -W 2 192.168.100.1 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Ping 192.168.100.1 (Callbox tunnel IP) OK${NC}"
else
    echo -e "${RED}❌ Ping 192.168.100.1 FAILED${NC}"
fi

if ping -c 2 -W 2 192.168.100.2 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Ping 192.168.100.2 (N3IWF tunnel IP) OK${NC}"
else
    echo -e "${RED}❌ Ping 192.168.100.2 FAILED${NC}"
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════"
echo -e "${BLUE}  📋 Summary & Recommendations${NC}"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Check if tunnel is established
if sudo ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
    echo -e "${GREEN}✅ IPsec tunnel is ESTABLISHED${NC}"
    echo -e "${GREEN}   Everything looks good!${NC}"
else
    echo -e "${RED}❌ IPsec tunnel is NOT established${NC}"
    echo ""
    echo -e "${YELLOW}Possible causes:${NC}"
    echo "1. Callbox simulator not creating config files"
    echo "2. IPsec service not started"
    echo "3. Config mismatch between callbox and N3IWF client"
    echo "4. Timing issue (tunnel needs more time to establish)"
    echo ""
    echo -e "${YELLOW}Recommended actions:${NC}"
    echo "1. Check callbox log: tail -f results/callbox.log"
    echo "2. Check N3IWF log: tail -f results/n3iwf_client.log"
    echo "3. Restart IPsec: sudo ipsec restart"
    echo "4. Wait 30 seconds and check again: sudo ipsec statusall"
    echo "5. Restart system: sudo ./stop_all.sh && sudo ./start_all.sh"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
