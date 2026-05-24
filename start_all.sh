#!/bin/bash
################################################################################
# start_all.sh - N3IWF + Edge AI Aquaculture System
################################################################################
# Semua output muncul di SATU terminal dengan label prefix berwarna.
# Bisa langsung di-screenshot tanpa perlu buka terminal lain.
#
# Usage:
#   chmod +x start_all.sh stop_all.sh
#   sudo ./start_all.sh
#
# Stop:
#   sudo ./stop_all.sh   (terminal lain)
#   atau tekan Ctrl+C di terminal ini
################################################################################

# ── Colors ────────────────────────────────────────────────────────────────── #
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
PIDS_FILE="$RESULTS_DIR/.pids"
LOG_DIR="$RESULTS_DIR/logs"

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

mkdir -p "$RESULTS_DIR" "$LOG_DIR"

# ── Helper: label-prefixed log stream ─────────────────────────────────────── #
# Usage: stream_log <color> <label> <logfile>
stream_log() {
    local color="$1"
    local label="$2"
    local logfile="$3"
    tail -F "$logfile" 2>/dev/null | while IFS= read -r line; do
        echo -e "${color}[${label}]${NC} $line"
    done &
}

# ── Cleanup on Ctrl+C ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo -e "${YELLOW}⏹  Ctrl+C detected — stopping all services...${NC}"
    # Kill all background jobs of THIS script
    kill $(jobs -p) 2>/dev/null || true
    # Also kill by PID file
    if [ -f "$PIDS_FILE" ]; then
        while IFS= read -r pid; do
            [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
    fi
    echo -e "${GREEN}✅ Semua service dihentikan.${NC}"
    echo -e "${YELLOW}   Data tersimpan di: $RESULTS_DIR${NC}"
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
    echo -e "${RED}❌ Harus dijalankan sebagai root${NC}"
    echo -e "${YELLOW}   Jalankan: sudo ./start_all.sh${NC}"
    exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo ~$REAL_USER)

# ═══════════════════════════════════════════════════════════════════════════ #
# [1/5] CEK DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [1/5] Cek Dependencies ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ python3 tidak terinstall${NC}"; exit 1
fi

python3 -c "import numpy" 2>/dev/null  || { echo -e "${YELLOW}   Installing numpy...${NC}"; pip3 install -q numpy; }
python3 -c "import flask"  2>/dev/null || { echo -e "${YELLOW}   Installing flask...${NC}"; pip3 install -q flask; }

if ! command -v ipsec &>/dev/null; then
    echo -e "${YELLOW}   strongSwan tidak terinstall — melewati IPsec${NC}"
    IPSEC_AVAILABLE=false
else
    IPSEC_AVAILABLE=true
fi

echo -e "${GREEN}✅ Dependencies OK${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [2/5] AKTIFKAN HOTSPOT WiFi
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [2/5] Aktifkan Hotspot N3IWF_AQUA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

HOTSPOT_OK=false

# Coba NetworkManager (modern RPi OS)
if command -v nmcli &>/dev/null; then
    if nmcli connection show --active | grep -q "N3IWF_AQUA"; then
        echo -e "${GREEN}✅ Hotspot N3IWF_AQUA sudah aktif (NetworkManager)${NC}"
        HOTSPOT_OK=true
    elif nmcli connection show N3IWF_AQUA &>/dev/null 2>&1; then
        echo -e "${CYAN}   Mengaktifkan hotspot N3IWF_AQUA...${NC}"
        nmcli connection up N3IWF_AQUA && HOTSPOT_OK=true && \
            echo -e "${GREEN}✅ Hotspot N3IWF_AQUA aktif${NC}"
    else
        echo -e "${CYAN}   Membuat hotspot baru N3IWF_AQUA...${NC}"
        nmcli device wifi hotspot ifname wlan0 ssid N3IWF_AQUA password skripsi2026 2>/dev/null && \
            nmcli connection modify N3IWF_AQUA ipv4.addresses 10.42.0.1/24 ipv4.method shared 2>/dev/null && \
            nmcli connection up N3IWF_AQUA 2>/dev/null && \
            HOTSPOT_OK=true && echo -e "${GREEN}✅ Hotspot N3IWF_AQUA dibuat dan aktif${NC}"
    fi
fi

# Fallback: hostapd
if [ "$HOTSPOT_OK" = false ] && command -v hostapd &>/dev/null; then
    systemctl start hostapd dnsmasq 2>/dev/null && \
        HOTSPOT_OK=true && echo -e "${GREEN}✅ Hotspot aktif (hostapd)${NC}"
fi

if [ "$HOTSPOT_OK" = false ]; then
    echo -e "${YELLOW}⚠️  Hotspot tidak bisa diaktifkan otomatis${NC}"
    echo -e "${YELLOW}   Jalankan manual: sudo bash fix_hotspot_nm.sh${NC}"
fi

# Tampilkan IP
RPI_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
[ -z "$RPI_IP" ] && RPI_IP=$(hostname -I | awk '{print $1}')
echo -e "${CYAN}   RPi IP: ${WHITE}$RPI_IP${NC}"
echo ""

# Enable IP forwarding
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true

# ═══════════════════════════════════════════════════════════════════════════ #
# [3/5] START CALLBOX SIMULATOR + N3IWF CLIENT (jika IPsec tersedia)
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [3/5] Start Callbox Simulator & N3IWF Client ━━━━━━━━━━━━━━━━━━━${NC}"

CALLBOX_LOG="$LOG_DIR/callbox.log"
N3IWF_LOG="$LOG_DIR/n3iwf_client.log"

rm -f "$PIDS_FILE"

if [ "$IPSEC_AVAILABLE" = true ]; then
    # Start callbox
    PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/callbox_simulator.py" \
        > "$CALLBOX_LOG" 2>&1 &
    CALLBOX_PID=$!
    echo "$CALLBOX_PID" >> "$PIDS_FILE"
    echo -e "${GREEN}✅ Callbox Simulator started (PID: $CALLBOX_PID)${NC}"
    sleep 3

    # Start N3IWF client
    PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/n3iwf/n3iwf_client.py" \
        > "$N3IWF_LOG" 2>&1 &
    N3IWF_PID=$!
    echo "$N3IWF_PID" >> "$PIDS_FILE"
    echo -e "${GREEN}✅ N3IWF Client started (PID: $N3IWF_PID)${NC}"
    sleep 5

    # Cek IPsec tunnel
    if ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
        echo -e "${GREEN}✅ IPsec Tunnel ESTABLISHED${NC}"
    else
        echo -e "${YELLOW}⚠️  IPsec tunnel belum established (melanjutkan tanpa IPsec)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  IPsec tidak tersedia — mode direct WiFi${NC}"
    touch "$CALLBOX_LOG" "$N3IWF_LOG"
    CALLBOX_PID=""
    N3IWF_PID=""
fi
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [4/5] START MAIN SYSTEM (run_real.py) + N3IWF SERVER (dashboard+TCP)
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${YELLOW}━━━ [4/5] Start Main System & Server ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

RUNREAL_LOG="$LOG_DIR/run_real.log"
SERVER_LOG="$LOG_DIR/n3iwf_server.log"

# Start run_real.py (main AI loop)
sudo -u "$REAL_USER" PYTHONPATH="$SCRIPT_DIR" python3 \
    "$SCRIPT_DIR/main/real/run_real.py" > "$RUNREAL_LOG" 2>&1 &
RUNREAL_PID=$!
echo "$RUNREAL_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ run_real.py started (PID: $RUNREAL_PID)${NC}"
echo -e "${CYAN}   TCP Server menunggu Pico WH di port ${WHITE}5000${NC}..."
sleep 2

# Start n3iwf/server.py (TCP + Flask dashboard dalam satu proses)
sudo -u "$REAL_USER" PYTHONPATH="$SCRIPT_DIR" python3 \
    "$SCRIPT_DIR/n3iwf/server.py" > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" >> "$PIDS_FILE"
echo -e "${GREEN}✅ N3IWF Server started (PID: $SERVER_PID)${NC}"
echo -e "${CYAN}   Dashboard: ${WHITE}http://$RPI_IP:8080${NC}"
sleep 2
echo ""

# ═══════════════════════════════════════════════════════════════════════════ #
# [5/5] SUMMARY + LIVE LOG STREAM
# ═══════════════════════════════════════════════════════════════════════════ #
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${GREEN}                    ✅ SISTEM BERJALAN                             ${BLUE}║${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  RPi IP      : ${WHITE}$RPI_IP${NC}"
echo -e "${BLUE}║${NC}  WiFi SSID   : ${WHITE}N3IWF_AQUA${NC}  Password: ${WHITE}skripsi2026${NC}"
echo -e "${BLUE}║${NC}  TCP Port    : ${WHITE}5000${NC}  ← Pico WH konek ke sini"
echo -e "${BLUE}║${NC}  Dashboard   : ${WHITE}http://$RPI_IP:8080${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  Log warna:"
echo -e "${BLUE}║${NC}  ${CYAN}[CALLBOX]${NC}  = Callbox 5G Simulator"
echo -e "${BLUE}║${NC}  ${MAGENTA}[N3IWF  ]${NC}  = N3IWF IPsec Client"
echo -e "${BLUE}║${NC}  ${GREEN}[MAIN   ]${NC}  = run_real.py (AI: RB→FQL→DQN)"
echo -e "${BLUE}║${NC}  ${YELLOW}[SERVER ]${NC}  = N3IWF Server (TCP+Dashboard)"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  MENUNGGU PICO WH... (nyalakan Pico WH sekarang)"
echo -e "${BLUE}║${NC}  Tekan ${RED}Ctrl+C${NC} untuk stop semua service"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Mulai stream semua log ke terminal ini ─────────────────────────────────── #
stream_log "$CYAN"    "CALLBOX" "$CALLBOX_LOG"
stream_log "$MAGENTA" "N3IWF  " "$N3IWF_LOG"
stream_log "$GREEN"   "MAIN   " "$RUNREAL_LOG"
stream_log "$YELLOW"  "SERVER " "$SERVER_LOG"

# ── Tunggu sampai Ctrl+C ───────────────────────────────────────────────────── #
echo -e "${CYAN}━━━ Live Log (semua service) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
wait
