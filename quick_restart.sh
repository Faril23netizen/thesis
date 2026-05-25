#!/bin/bash
################################################################################
# quick_restart.sh - Bersihkan proses lama lalu restart sistem
################################################################################
# Gunakan ini jika RPi dimatikan tanpa stop_all.sh (proses orphan)
#
# Usage:
#   chmod +x quick_restart.sh
#   sudo ./quick_restart.sh
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${YELLOW}                    Quick Clean Restart                             ${BLUE}║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Harus dijalankan sebagai root: sudo ./quick_restart.sh${NC}"
    exit 1
fi

# [1] Chmod scripts
echo -e "${YELLOW}[1/4] Set permission scripts...${NC}"
chmod +x start_all.sh stop_all.sh
echo -e "${GREEN}✅ OK${NC}"
echo ""

# [2] Kill orphan processes
echo -e "${YELLOW}[2/4] Membersihkan proses orphan...${NC}"
FOUND=0
for script in callbox_simulator.py n3iwf_client.py run_real.py server.py dashboard.py; do
    if pgrep -f "$script" >/dev/null 2>&1; then
        echo -e "  Killing $script..."
        pkill -9 -f "$script" 2>/dev/null || true
        FOUND=1
    fi
done

if pgrep -f "tshark" >/dev/null 2>&1; then
    echo -e "  Killing tshark..."
    pkill -9 -f "tshark" 2>/dev/null || true
    pkill -9 -f "capture_qos.sh" 2>/dev/null || true
    FOUND=1
fi

[ $FOUND -eq 1 ] && sleep 2 && echo -e "${GREEN}✅ Proses orphan dihapus${NC}" \
                 || echo -e "${GREEN}✅ Tidak ada proses orphan${NC}"
echo ""

# [3] Stop IPsec
echo -e "${YELLOW}[3/4] Stop IPsec (jika berjalan)...${NC}"
if command -v ipsec &>/dev/null && ipsec status >/dev/null 2>&1; then
    ipsec stop >/dev/null 2>&1 || true
    sleep 2
    echo -e "${GREEN}✅ IPsec stopped${NC}"
else
    echo -e "${GREEN}✅ IPsec tidak berjalan${NC}"
fi
rm -f results/.pids /var/run/charon.pid /var/run/starter.charon.pid 2>/dev/null || true
echo ""

# [4] Start ulang
echo -e "${YELLOW}[4/4] Memulai sistem...${NC}"
echo ""
exec ./start_all.sh
