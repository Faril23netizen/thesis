#!/bin/bash
# =============================================================
# setup_n3iwf.sh — RPi5 N3IWF Setup Script
# =============================================================
# Jalankan SEKALI di Raspberry Pi 5 sebelum pengujian pertama.
# Script ini:
#   1. Install strongSwan (IPsec client)
#   2. Copy konfigurasi IPsec
#   3. Aktifkan dan mulai tunnel IPsec ke Amarisoft N3IWF
#
# Usage:
#   chmod +x n3iwf/setup_n3iwf.sh
#   sudo bash n3iwf/setup_n3iwf.sh
# =============================================================

set -e  # Hentikan jika ada error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "======================================================="
echo " N3IWF Setup — Raspberry Pi 5 sebagai N3IWUE"
echo "======================================================="

# --- Cek root ---
if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Script ini harus dijalankan sebagai root (sudo)."
    exit 1
fi

# --- 1. Install strongSwan ---
echo "[1/4] Installing strongSwan..."
apt-get update -qq
apt-get install -y strongswan strongswan-pki libcharon-extra-plugins

# --- 2. Copy konfigurasi IPsec ---
echo "[2/4] Copying IPsec configuration..."
cp "$SCRIPT_DIR/ipsec.conf"    /etc/ipsec.conf
cp "$SCRIPT_DIR/ipsec.secrets" /etc/ipsec.secrets

# Amankan file secrets
chmod 600 /etc/ipsec.secrets
echo "      ipsec.conf & ipsec.secrets copied."

# --- 3. Aktifkan strongSwan sebagai service ---
echo "[3/4] Enabling strongSwan service..."
systemctl enable strongswan-starter
systemctl restart strongswan-starter

# Tunggu sebentar
sleep 3

# --- 4. Cek status tunnel ---
echo "[4/4] Checking IPsec tunnel status..."
ipsec statusall

echo ""
echo "======================================================="
echo " Setup selesai!"
echo " Cek koneksi: sudo ipsec statusall"
echo " Lihat log  : sudo journalctl -u strongswan-starter -f"
echo "======================================================="
echo ""
echo "[CATATAN] Pastikan Amarisoft N3IWF Callbox sudah berjalan"
echo "          dengan konfigurasi n3iwf/n3iwf_amarisoft.cfg"
echo "          sebelum menjalankan pengujian utama."
