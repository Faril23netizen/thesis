#!/bin/bash
# =============================================================
# rpi5_setup.sh — Raspberry Pi 5 Full Setup Script
# =============================================================
# Jalankan SATU KALI di Raspberry Pi 5 yang baru/bersih.
#
# Script ini melakukan:
#   1. Update sistem & install dependensi Python
#   2. Install strongSwan (IPsec untuk N3IWF)
#   3. Konfigurasi IPsec tunnel ke Amarisoft N3IWF
#   4. Install Python packages (Flask, NumPy, PySerial, dll)
#   5. Install SystemD service agar sistem auto-start saat booting
#
# Usage:
#   chmod +x rpi5_setup.sh
#   sudo bash rpi5_setup.sh
# =============================================================

set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# ── Warna untuk output ──────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Cek root ─────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    error "Script ini harus dijalankan sebagai root. Gunakan: sudo bash rpi5_setup.sh"
fi

echo ""
echo "==========================================================="
echo "  Raspberry Pi 5 — N3IWF Edge Node Setup"
echo "  Aquaculture FQL-DQN Thesis"
echo "==========================================================="
echo ""

# ── Step 1: Update sistem ─────────────────────────────────────────
info "Step 1/6 — Update & upgrade sistem..."
apt-get update -qq
apt-get upgrade -y -qq
info "Sistem berhasil diupdate."

# ── Step 2: Install dependensi sistem ────────────────────────────
info "Step 2/6 — Install dependensi sistem..."
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    net-tools \
    strongswan \
    strongswan-pki \
    libcharon-extra-plugins \
    build-essential
info "Dependensi sistem berhasil diinstall."

# ── Step 3: Install Python packages ──────────────────────────────
info "Step 3/6 — Install Python packages..."
pip3 install --quiet \
    flask \
    flask-cors \
    numpy \
    matplotlib \
    pyserial

# Coba install PyTorch (opsional, fallback ke numpy jika gagal)
info "  Mencoba install PyTorch (opsional)..."
pip3 install torch --index-url https://download.pytorch.org/whl/cpu --quiet 2>/dev/null && \
    info "  PyTorch berhasil diinstall (DQN akan pakai PyTorch backend)." || \
    warn "  PyTorch tidak tersedia. DQN akan pakai numpy backend (tetap berfungsi)."

info "Python packages berhasil diinstall."

# ── Step 4: Konfigurasi IPsec untuk N3IWF ────────────────────────
info "Step 4/6 — Konfigurasi IPsec (strongSwan) untuk N3IWF..."

# Cek apakah file konfigurasi ada
if [ ! -f "$SCRIPT_DIR/n3iwf/ipsec.conf" ]; then
    warn "File n3iwf/ipsec.conf tidak ditemukan. Skip konfigurasi IPsec."
    warn "Jalankan manual: sudo bash n3iwf/setup_n3iwf.sh setelah edit IP-nya."
else
    cp "$SCRIPT_DIR/n3iwf/ipsec.conf"    /etc/ipsec.conf
    cp "$SCRIPT_DIR/n3iwf/ipsec.secrets" /etc/ipsec.secrets
    chmod 600 /etc/ipsec.secrets

    systemctl enable strongswan-starter
    systemctl restart strongswan-starter
    sleep 3

    if ipsec statusall 2>/dev/null | grep -q "ESTABLISHED"; then
        info "IPsec tunnel ke Amarisoft N3IWF: ESTABLISHED ✓"
    else
        warn "IPsec tunnel belum terhubung."
        warn "Pastikan Amarisoft N3IWF Callbox sudah aktif, lalu jalankan: sudo ipsec restart"
    fi
fi

# ── Step 5: Buat folder results ───────────────────────────────────
info "Step 5/6 — Membuat folder results..."
mkdir -p "$SCRIPT_DIR/results/hasil_real"
mkdir -p "$SCRIPT_DIR/results/simulation"
chmod -R 755 "$SCRIPT_DIR/results"
info "Folder results dibuat: results/hasil_real/ dan results/simulation/"

# ── Step 6: Install SystemD Service ──────────────────────────────
info "Step 6/6 — Install SystemD service (auto-start saat boot)..."

# Update path di aquaculture.service sesuai lokasi instalasi
SERVICE_FILE="$SCRIPT_DIR/aquaculture.service"
if [ -f "$SERVICE_FILE" ]; then
    # Ganti path /home/ubuntu/thesis dengan path aktual
    sed -i "s|/home/ubuntu/thesis|$SCRIPT_DIR|g" "$SERVICE_FILE"

    cp "$SERVICE_FILE" /etc/systemd/system/aquaculture.service
    systemctl daemon-reload
    systemctl enable aquaculture
    info "Service aquaculture berhasil diinstall."
    info "  Start : sudo systemctl start aquaculture"
    info "  Status: sudo systemctl status aquaculture"
    info "  Log   : tail -f $SCRIPT_DIR/results/hasil_real/service.log"
else
    warn "File aquaculture.service tidak ditemukan. Skip install service."
fi

# ── Selesai ───────────────────────────────────────────────────────
echo ""
echo "==========================================================="
echo -e "  ${GREEN}Setup selesai!${NC}"
echo "==========================================================="
echo ""
echo "  Langkah selanjutnya:"
echo ""
echo "  1. Edit IP di n3iwf/ipsec.conf:"
echo "       left  = IP Raspberry Pi ini    (cek: hostname -I)"
echo "       right = IP Amarisoft Callbox"
echo ""
echo "  2. Pastikan n3iwf_amarisoft.cfg sudah dikopi ke Callbox"
echo "     dan lten3iwf sudah berjalan di sana."
echo ""
echo "  3. Flash firmware ke Pico WH:"
echo "     Edit main.c: N3IWF_SERVER_IP = IP RPi5 ini"
echo "     Build & flash .uf2 ke Pico."
echo ""
echo "  4. Jalankan sistem:"
echo "       ./start_edge.sh"
echo ""
echo "  📖 Lihat panduan lengkap: n3iwf/README.md"
echo ""
