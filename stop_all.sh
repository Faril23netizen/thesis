#!/bin/bash
################################################################################
# stop_all.sh - Stop Complete N3IWF + Edge AI System
################################################################################
# Usage:
#   chmod +x stop_all.sh
#   sudo ./stop_all.sh
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
PIDS_FILE="$RESULTS_DIR/.pids"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${RED}           Menghentikan N3IWF + Edge AI System                     ${BLUE}║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Harus dijalankan sebagai root: sudo ./stop_all.sh${NC}"
    exit 1
fi

# [1] Hentikan dari PID file
echo -e "${YELLOW}[1/4] Menghentikan service via PID file...${NC}"
if [ -f "$PIDS_FILE" ]; then
    while IFS= read -r pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            PROC=$(ps -p "$pid" -o comm= 2>/dev/null || echo "?")
            echo -e "  Stopping $PROC (PID: $pid)..."
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        fi
    done < "$PIDS_FILE"
    rm -f "$PIDS_FILE"
    echo -e "${GREEN}✅ Selesai${NC}"
else
    echo -e "${YELLOW}⚠️  Tidak ada PID file${NC}"
fi
echo ""

# [2] Pastikan semua Python process terkait dihentikan
echo -e "${YELLOW}[2/4] Menghentikan Python processes...${NC}"
for script in callbox_simulator.py n3iwf_client.py run_real.py server.py; do
    if pgrep -f "$script" >/dev/null 2>&1; then
        echo -e "  Stopping $script..."
        pkill -TERM -f "$script" 2>/dev/null || true
        sleep 1
        pkill -9 -f "$script" 2>/dev/null || true
        echo -e "  ${GREEN}✅ Stopped${NC}"
    fi
done

# Hentikan tshark/pcap capture
if pgrep -f "tshark" >/dev/null 2>&1; then
    echo -e "  Stopping tshark (QoS Capture)..."
    pkill -TERM -f "tshark" 2>/dev/null || true
    pkill -TERM -f "capture_qos.sh" 2>/dev/null || true
    sleep 1
    echo -e "  ${GREEN}✅ Stopped${NC}"
fi

echo -e "${GREEN}✅ Selesai${NC}"
echo ""

# [3] Hentikan IPsec
echo -e "${YELLOW}[3/4] Menghentikan IPsec...${NC}"
if command -v ipsec &>/dev/null && ipsec status >/dev/null 2>&1; then
    ipsec stop >/dev/null 2>&1 || true
    rm -f /var/run/charon.pid /var/run/starter.charon.pid 2>/dev/null || true
    echo -e "${GREEN}✅ IPsec stopped${NC}"
else
    echo -e "${YELLOW}⚠️  IPsec tidak running${NC}"
fi
rm -f /tmp/ipsec_callbox.conf /tmp/ipsec_callbox.secrets \
       /tmp/ipsec_n3iwf.conf  /tmp/ipsec_n3iwf.secrets 2>/dev/null || true
echo ""

# [4] Verifikasi
echo -e "${YELLOW}[4/4] Verifikasi...${NC}"
ALL_STOPPED=true
for script in callbox_simulator.py n3iwf_client.py run_real.py server.py; do
    if pgrep -f "$script" >/dev/null 2>&1; then
        echo -e "${RED}❌ Masih running: $script${NC}"
        ALL_STOPPED=false
    fi
done

if [ "$ALL_STOPPED" = true ]; then
    echo -e "${GREEN}✅ Semua service dihentikan${NC}"
fi
echo ""

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${GREEN}                      ✅ SISTEM DIHENTIKAN                         ${BLUE}║${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  Log tersimpan di:  ${YELLOW}results/logs/${NC}"
echo -e "${BLUE}║${NC}  Data tersimpan di: ${YELLOW}results/hasil_real/${NC}"
echo -e "${BLUE}║${NC}  Restart: ${GREEN}sudo ./start_all.sh${NC}"
echo -e "${BLUE}║${NC}  Analisis: ${GREEN}python3 analyze_all.py${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
