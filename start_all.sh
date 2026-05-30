#!/bin/bash
################################################################################
# start_all.sh - Aquaculture NH3 Risk Monitoring System
################################################################################
# Architecture:
#   run_real.py        → TCP port 5000 (Pico WH connects here) + AI RB→FQL→DQN
#   n3iwf/server.py    → ONLY if IPsec is active (separate, also port 5000,
#                        but not run simultaneously with run_real.py)
#
# What appears in this terminal:
#   - Startup banner, status for each step
#   - Real-time log from run_real.py (main AI log + Pico connections)
#   - Callbox/N3IWF runs silently in the background
#
# Usage:
#   sudo ./start_all.sh
# Stop:
#   sudo ./stop_all.sh  OR  Ctrl+C
################################################################################

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; WHITE='\033[1;37m'
GRAY='\033[0;90m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
LOG_DIR="$RESULTS_DIR/logs"
PIDS_FILE="$RESULTS_DIR/.pids"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
mkdir -p "$LOG_DIR" "$RESULTS_DIR/hasil_real"

# ── Cleanup on Ctrl+C ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo -e "${YELLOW}⏹  Stopping all services...${NC}"
    kill $(jobs -p) 2>/dev/null || true
    [ -f "$PIDS_FILE" ] && while IFS= read -r pid; do
        [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
    done < "$PIDS_FILE" && rm -f "$PIDS_FILE"
    echo -e "${GREEN}✅ Done. Data saved to: results/hasil_real/${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ═══════════════════════════════════════════════════════════════════════════ #
clear
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${WHITE}       Aquaculture NH₃ Risk Monitoring — N3IWF Edge AI             ${BLUE}║${NC}"
echo -e "${BLUE}║${CYAN}       Raspberry Pi  ←→  Pico WH  |  Rule-Based → FQL → DQN        ${BLUE}║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Must be run as root: sudo ./start_all.sh${NC}"; exit 1
fi
REAL_USER="${SUDO_USER:-$USER}"
rm -f "$PIDS_FILE"

# ═══════════════════════════════════════════════════════════════════════════ #
# [1/4] DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [1/4] Check Dependencies ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
python3 -c "import numpy" 2>/dev/null || pip3 install -q numpy
python3 -c "import flask"  2>/dev/null || pip3 install -q flask
command -v ipsec &>/dev/null && IPSEC_AVAILABLE=true || IPSEC_AVAILABLE=false
echo -e "${GREEN}✅ OK${NC}  │  IPsec: $([ "$IPSEC_AVAILABLE" = true ] && echo "${GREEN}available${NC}" || echo "${GRAY}not available${NC}")"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [2/4] HOTSPOT
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [2/4] Enable Hotspot N3IWF_AQUA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
HOTSPOT_OK=false
if command -v nmcli &>/dev/null; then
    if nmcli connection show --active 2>/dev/null | grep -q "N3IWF_AQUA"; then
        echo -e "${GREEN}✅ Hotspot N3IWF_AQUA is already active${NC}"
        HOTSPOT_OK=true
    elif nmcli connection show N3IWF_AQUA &>/dev/null 2>&1; then
        nmcli connection up N3IWF_AQUA 2>/dev/null && HOTSPOT_OK=true && \
            echo -e "${GREEN}✅ Hotspot N3IWF_AQUA active${NC}"
    else
        echo -e "${CYAN}   Creating hotspot N3IWF_AQUA...${NC}"
        nmcli device wifi hotspot ifname wlan0 ssid N3IWF_AQUA password skripsi2026 2>/dev/null
        nmcli connection modify N3IWF_AQUA ipv4.addresses 10.42.0.1/24 ipv4.method shared 2>/dev/null
        nmcli connection up N3IWF_AQUA 2>/dev/null && HOTSPOT_OK=true && \
            echo -e "${GREEN}✅ Hotspot N3IWF_AQUA created and active${NC}"
    fi
fi
[ "$HOTSPOT_OK" = false ] && command -v hostapd &>/dev/null && \
    systemctl start hostapd dnsmasq 2>/dev/null && HOTSPOT_OK=true && \
    echo -e "${GREEN}✅ Hotspot active (hostapd)${NC}"
[ "$HOTSPOT_OK" = false ] && \
    echo -e "${YELLOW}⚠️  Hotspot not detected — enable it manually${NC}"

sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
RPI_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
[ -z "$RPI_IP" ] && RPI_IP=$(hostname -I | awk '{print $1}')
echo -e "${CYAN}   RPi IP : ${WHITE}$RPI_IP${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [3/4] N3IWF INFRASTRUCTURE — IPsec Tunnel + Callbox Simulator
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [3/4] N3IWF Infrastructure (IPsec Tunnel + Callbox) ━━━━━━━━━━━━━${NC}"

# Setup N3IWF IPsec tunnel (namespace + veth + AES-256-GCM ESP)
echo -e "${CYAN}   Setting up N3IWF IPsec tunnel...${NC}"
if bash "$SCRIPT_DIR/setup_n3iwf_tunnel.sh" setup 2>/dev/null; then
    # Verify the tunnel is truly established
    SA_COUNT=$(ip xfrm state list 2>/dev/null | grep -c "src 172.16.10." || echo 0)
    if [ "$SA_COUNT" -ge 2 ]; then
        echo -e "${GREEN}✅ N3IWF IPsec Tunnel ESTABLISHED${NC}  ${GRAY}(AES-256-GCM ESP, $SA_COUNT SAs)${NC}"
        IPSEC_AVAILABLE=true
    else
        echo -e "${YELLOW}⚠️  IPsec tunnel not yet established — try manually: sudo ./setup_n3iwf_tunnel.sh${NC}"
        IPSEC_AVAILABLE=false
    fi
else
    echo -e "${YELLOW}⚠️  setup_n3iwf_tunnel.sh failed — continuing without real tunnel${NC}"
    IPSEC_AVAILABLE=false
fi

# Start Callbox Simulator (always, since it manages 5G Core stats + QoS)
PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/callbox_simulator.py" \
    > "$LOG_DIR/callbox.log" 2>&1 &
echo "$!" >> "$PIDS_FILE"
echo -e "${GREEN}✅ Callbox Simulator${NC}  ${GRAY}→ logs/callbox.log${NC}"
sleep 2
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [4/4] MAIN SYSTEM — run_real.py (TCP port 5000 + AI RB→FQL→DQN)
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [4/4] Start Main System (run_real.py) ━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
RUNREAL_LOG="$LOG_DIR/run_real.log"

PYTHONPATH="$SCRIPT_DIR" python3 \
    "$SCRIPT_DIR/main/real/run_real.py" > "$RUNREAL_LOG" 2>&1 &
RUNREAL_PID=$!
echo "$RUNREAL_PID" >> "$PIDS_FILE"
sleep 2

# Check if it started successfully
if kill -0 "$RUNREAL_PID" 2>/dev/null; then
    echo -e "${GREEN}✅ run_real.py running${NC}  ${GRAY}(PID $RUNREAL_PID)${NC}"
    echo -e "${CYAN}   TCP Port : ${WHITE}5000${NC}  ← Pico WH connects here"
else
    echo -e "${RED}❌ run_real.py failed to start! Check error:${NC}"
    tail -20 "$RUNREAL_LOG"
    exit 1
fi

# Start dashboard (port 8080)
DASH_LOG="$LOG_DIR/dashboard.log"
PYTHONPATH="$SCRIPT_DIR" python3 \
    "$SCRIPT_DIR/main/real/dashboard.py" > "$DASH_LOG" 2>&1 &
DASH_PID=$!
echo "$DASH_PID" >> "$PIDS_FILE"
sleep 1
echo -e "${GREEN}✅ Dashboard running${NC}  ${GRAY}(PID $DASH_PID)${NC}"
echo -e "${CYAN}   URL : ${WHITE}http://$RPI_IP:8080${NC}  ← open in browser"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [5/4] QOS CAPTURE (Background)
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [*] Starting Wireshark Capture (QoS) ━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
chmod +x capture_qos.sh
sudo ./capture_qos.sh > "$LOG_DIR/capture_qos.log" 2>&1 &
echo "$!" >> "$PIDS_FILE"
echo -e "${GREEN}✅ QoS Capture (tshark) running${NC} ${GRAY}→ results/network/qos_real.pcap${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
#  STATUS BOX
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${GREEN}                    ✅ SYSTEM RUNNING                              ${BLUE}║${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  WiFi    : ${WHITE}N3IWF_AQUA${NC}  (password: ${WHITE}skripsi2026${NC})"
echo -e "${BLUE}║${NC}  RPi IP  : ${WHITE}$RPI_IP${NC}  │  TCP Port: ${WHITE}5000${NC}"
echo -e "${BLUE}║${NC}  AI Mode : ${WHITE}Rule-Based → FQL → DQN${NC}  (progressive, automatic)"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  ${YELLOW}► Power on Pico WH — wait until it connects to WiFi${NC}"
echo -e "${BLUE}║${NC}  Press ${RED}Ctrl+C${NC} to stop all services"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}━━━ Live Log [run_real.py] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Stream log run_real.py ke terminal dengan highlight warna ─────────────── #
tail -F "$RUNREAL_LOG" 2>/dev/null | while IFS= read -r line; do
    if echo "$line" | grep -qE "Pico connected|PHASE [BCDE]"; then
        echo -e "${GREEN}$line${NC}"
    elif echo "$line" | grep -qE "\[RB\]|\[FQL\]|\[DQN\]"; then
        echo -e "${WHITE}$line${NC}"
    elif echo "$line" | grep -qE "Q-table|CONVERGED|DQN training|PHASE"; then
        echo -e "${CYAN}$line${NC}"
    elif echo "$line" | grep -qE "ERROR|FATAL|error"; then
        echo -e "${RED}$line${NC}"
    elif echo "$line" | grep -qE "WARNING|WARN|warning"; then
        echo -e "${YELLOW}$line${NC}"
    elif echo "$line" | grep -qE "Waiting for Pico|PHASE A"; then
        echo -e "${CYAN}$line${NC}"
    else
        echo -e "${GRAY}$line${NC}"
    fi
done &

wait
