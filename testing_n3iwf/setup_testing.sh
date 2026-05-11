#!/bin/bash
# =============================================================
# setup_testing.sh — Local Wi-Fi Testing Setup Script
# =============================================================
# Jalankan SATU KALI di Raspberry Pi 5 yang baru/bersih.
# Script ini menginstall dependensi Python yang dibutuhkan
# (tanpa install IPsec/strongSwan).
#
# Usage:
#   chmod +x setup_testing.sh
#   sudo bash setup_testing.sh
# =============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

if [ "$EUID" -ne 0 ]; then
    error "Script ini harus dijalankan sebagai root. Gunakan: sudo bash setup_testing.sh"
fi

echo ""
echo "==========================================================="
echo "  Raspberry Pi 5 — Local Wi-Fi Testing Setup"
echo "==========================================================="
echo ""

info "Step 1/3 — Update sistem & install python3-pip..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl
info "Sistem berhasil diupdate."

info "Step 2/3 — Install Python packages (Flask, NumPy, dkk)..."
# Gunakan argumen --break-system-packages jika PIP rewel di Debian/Ubuntu terbaru
pip3 install --quiet flask flask-cors numpy matplotlib pyserial --break-system-packages || \
pip3 install --quiet flask flask-cors numpy matplotlib pyserial

info "  Mencoba install PyTorch (opsional)..."
pip3 install torch --index-url https://download.pytorch.org/whl/cpu --quiet --break-system-packages 2>/dev/null || \
pip3 install torch --index-url https://download.pytorch.org/whl/cpu --quiet 2>/dev/null && \
    info "  PyTorch berhasil diinstall (DQN siap)." || \
    warn "  PyTorch tidak tersedia. (Silakan install manual jika butuh DQN training lokal)."

info "Step 3/3 — Membuat folder results..."
mkdir -p results/hasil_real
chmod -R 755 results
info "Folder results/hasil_real berhasil dibuat."

echo ""
echo "==========================================================="
echo -e "  ${GREEN}Setup selesai!${NC}"
echo "==========================================================="
echo "  Sekarang Anda bisa menjalankan sistem dengan perintah:"
echo "    ./start_edge.sh"
echo ""
