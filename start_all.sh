#!/bin/bash
################################################################################
# start_all.sh - N3IWF + Edge AI Aquaculture System
################################################################################
# Semua output muncul di SATU terminal.
# Callbox & N3IWF berjalan di background (log disimpan, hanya error tampil).
# Log utama yang tampil: [SERVER] = TCP Pico + AI inference + Dashboard
#
# Usage:
#   sudo ./start_all.sh
# Stop:
#   sudo ./stop_all.sh  (terminal lain)  ATAU tekan Ctrl+C
################################################################################

# ── Colors ────────────────────────────────────────────────────────────────── #
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'
WHITE='\033[1;37m'; GRAY='\033[0;90m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
LOG_DIR="$RESULTS_DIR/logs"
PIDS_FILE="$RESULTS_DIR/.pids"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
mkdir -p "$LOG_DIR"

# ── Cleanup on Ctrl+C ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo -e "${YELLOW}⏹  Menghentikan semua service...${NC}"
    kill $(jobs -p) 2>/dev/null || true
    if [ -f "$PIDS_FILE" ]; then
        while IFS= read -r pid; do
            [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
    fi
    echo -e "${GREEN}✅ Semua service dihentikan. Data tersimpan di: $LOG_DIR${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ═══════════════════════════════════════════════════════════════════════════ #
#                             STARTUP BANNER                                   #
# ═══════════════════════════════════════════════════════════════════════════ #
clear
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${WHITE}       Aquaculture NH₃ Risk Monitoring — N3IWF Edge AI             ${BLUE}║${NC}"
echo -e "${BLUE}║${CYAN}       Raspberry Pi  ←→  Pico WH  |  Rule-Based → FQL → DQN        ${BLUE}║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Root check ────────────────────────────────────────────────────────────── #
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Harus dijalankan sebagai root: sudo ./start_all.sh${NC}"; exit 1
fi
REAL_USER="${SUDO_USER:-$USER}"

# ═══════════════════════════════════════════════════════════════════════════ #
# [1/4] CEK DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [1/4] Cek Dependencies ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
python3 -c "import numpy" 2>/dev/null || { echo -e "${CYAN}   Installing numpy...${NC}"; pip3 install -q numpy; }
python3 -c "import flask"  2>/dev/null || { echo -e "${CYAN}   Installing flask...${NC}";  pip3 install -q flask; }
command -v ipsec &>/dev/null && IPSEC_AVAILABLE=true || IPSEC_AVAILABLE=false
echo -e "${GREEN}✅ Dependencies OK  │  IPsec: $([ "$IPSEC_AVAILABLE" = true ] && echo "tersedia" || echo "tidak tersedia")${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [2/4] AKTIFKAN HOTSPOT WiFi
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [2/4] Aktifkan Hotspot N3IWF_AQUA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
HOTSPOT_OK=false

if command -v nmcli &>/dev/null; then
    if nmcli connection show --active | grep -q "N3IWF_AQUA"; then
        echo -e "${GREEN}✅ Hotspot N3IWF_AQUA sudah aktif${NC}"
        HOTSPOT_OK=true
    elif nmcli connection show N3IWF_AQUA &>/dev/null 2>&1; then
        echo -e "${CYAN}   Mengaktifkan hotspot N3IWF_AQUA...${NC}"
        nmcli connection up N3IWF_AQUA 2>/dev/null && HOTSPOT_OK=true && \
            echo -e "${GREEN}✅ Hotspot N3IWF_AQUA aktif${NC}"
    else
        echo -e "${CYAN}   Membuat hotspot baru N3IWF_AQUA (SSID=N3IWF_AQUA, pass=skripsi2026)...${NC}"
        nmcli device wifi hotspot ifname wlan0 ssid N3IWF_AQUA password skripsi2026 2>/dev/null
        nmcli connection modify N3IWF_AQUA ipv4.addresses 10.42.0.1/24 ipv4.method shared 2>/dev/null
        nmcli connection up N3IWF_AQUA 2>/dev/null && HOTSPOT_OK=true && \
            echo -e "${GREEN}✅ Hotspot N3IWF_AQUA dibuat dan aktif${NC}"
    fi
fi

if [ "$HOTSPOT_OK" = false ] && command -v hostapd &>/dev/null; then
    systemctl start hostapd dnsmasq 2>/dev/null && HOTSPOT_OK=true && \
        echo -e "${GREEN}✅ Hotspot aktif (hostapd)${NC}"
fi

[ "$HOTSPOT_OK" = false ] && \
    echo -e "${YELLOW}⚠️  Hotspot tidak terdeteksi — pastikan aktif secara manual${NC}"

sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true

RPI_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
[ -z "$RPI_IP" ] && RPI_IP=$(hostname -I | awk '{print $1}')
echo -e "${CYAN}   RPi IP: ${WHITE}$RPI_IP${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [3/4] START CALLBOX + N3IWF CLIENT (background, hanya log error tampil)
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [3/4] Start Infrastruktur N3IWF (background) ━━━━━━━━━━━━━━━━━━━${NC}"
CALLBOX_LOG="$LOG_DIR/callbox.log"
N3IWF_LOG="$LOG_DIR/n3iwf_client.log"
rm -f "$PIDS_FILE"

if [ "$IPSEC_AVAILABLE" = true ]; then
    PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/callbox_simulator.py" \
        > "$CALLBOX_LOG" 2>&1 &
    CALLBOX_PID=$!; echo "$CALLBOX_PID" >> "$PIDS_FILE"
    echo -e "${GREEN}✅ Callbox Simulator started${NC}  ${GRAY}(PID $CALLBOX_PID — log: logs/callbox.log)${NC}"
    sleep 3

    PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/n3iwf_client.py" \
        > "$N3IWF_LOG" 2>&1 &
    N3IWF_PID=$!; echo "$N3IWF_PID" >> "$PIDS_FILE"
    echo -e "${GREEN}✅ N3IWF Client started${NC}  ${GRAY}(PID $N3IWF_PID — log: logs/n3iwf_client.log)${NC}"
    sleep 5

    ipsec statusall 2>/dev/null | grep -q "ESTABLISHED" && \
        echo -e "${GREEN}✅ IPsec Tunnel ESTABLISHED${NC}" || \
        echo -e "${YELLOW}⚠️  IPsec tunnel belum established (lanjut tanpa IPsec)${NC}"
else
    echo -e "${YELLOW}⚠️  IPsec tidak tersedia — mode direct WiFi${NC}"
    touch "$CALLBOX_LOG" "$N3IWF_LOG"
fi
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [4/4] START N3IWF SERVER (TCP port 5000 + Dashboard port 8080)
#        ← Satu-satunya service yang listen port 5000 untuk Pico WH
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [4/4] Start N3IWF Server (TCP+AI+Dashboard) ━━━━━━━━━━━━━━━━━━━━${NC}"
SERVER_LOG="$LOG_DIR/n3iwf_server.log"

sudo -u "$REAL_USER" PYTHONPATH="$SCRIPT_DIR" python3 \
    "$SCRIPT_DIR/n3iwf/server.py" > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!; echo "$SERVER_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ N3IWF Server started${NC}  ${GRAY}(PID $SERVER_PID)${NC}"
echo -e "${CYAN}   TCP Port : ${WHITE}5000${NC}  ← Pico WH konek ke sini"
echo -e "${CYAN}   Dashboard: ${WHITE}http://$RPI_IP:8080${NC}"
sleep 2
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
#  STATUS BOX + LIVE LOG STREAM
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${GREEN}                    ✅ SISTEM BERJALAN                             ${BLUE}║${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  WiFi SSID   : ${WHITE}N3IWF_AQUA${NC}  │  Password : ${WHITE}skripsi2026${NC}"
echo -e "${BLUE}║${NC}  RPi IP      : ${WHITE}$RPI_IP${NC}  │  TCP Port : ${WHITE}5000${NC}"
echo -e "${BLUE}║${NC}  Dashboard   : ${WHITE}http://$RPI_IP:8080${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  ${GRAY}Infrastruktur (callbox/N3IWF) berjalan di background${NC}"
echo -e "${BLUE}║${NC}  ${GRAY}Log infra: results/logs/callbox.log & n3iwf_client.log${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  ${YELLOW}► Nyalakan Pico WH sekarang — tunggu sampai konek${NC}"
echo -e "${BLUE}║${NC}  Tekan ${RED}Ctrl+C${NC} untuk stop semua service"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}━━━ Live Log [N3IWF Server — TCP + AI Inference] ━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Stream HANYA log server (yang penting) ke terminal
# Callbox & N3IWF berjalan diam di background, lognya di file
tail -F "$SERVER_LOG" 2>/dev/null | while IFS= read -r line; do
    # Warna berbeda untuk event penting
    if echo "$line" | grep -qE "\[TCP\] Pico connected|connected from"; then
        echo -e "${GREEN}$line${NC}"
    elif echo "$line" | grep -qE "\[REAL\]"; then
        echo -e "${WHITE}$line${NC}"
    elif echo "$line" | grep -qE "ERROR|error|FATAL"; then
        echo -e "${RED}$line${NC}"
    elif echo "$line" | grep -qE "WARNING|warning|⚠"; then
        echo -e "${YELLOW}$line${NC}"
    elif echo "$line" | grep -qE "\[TCP\]|Waiting|Pico"; then
        echo -e "${CYAN}$line${NC}"
    else
        echo -e "${GRAY}$line${NC}"
    fi
done &

wait
