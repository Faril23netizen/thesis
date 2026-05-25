#!/bin/bash
# capture_qos.sh
# Skrip untuk merekam lalu lintas jaringan (QoS) menggunakan tshark.
# Hasil rekaman akan disimpan di results/network/qos_real.pcap
# Dapat dibuka di Wireshark (Windows) untuk analisis QoS (Bandwidth, Jitter, Packet Loss).

mkdir -p results/network

echo "=========================================================="
echo "  [N3IWF QoS Monitor] Memulai Perekaman Wireshark (tshark)"
echo "=========================================================="

# Cek apakah tshark sudah terinstall
if ! command -v tshark &> /dev/null
then
    echo "tshark tidak ditemukan. Melakukan instalasi otomatis..."
    echo "CATATAN: Pastikan Raspberry Pi Anda memiliki KONEKSI INTERNET yang aktif!"
    
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y tshark
    
    # Verifikasi apakah instalasi benar-benar berhasil
    if ! command -v tshark &> /dev/null; then
        echo "=========================================================="
        echo "ERROR FATAL: Gagal mengunduh tshark!"
        echo "Penyebab: Raspberry Pi Anda tidak terhubung ke internet (Gagal Resolusi DNS)."
        echo "Solusi: Hubungkan Raspberry Pi ke internet (via WiFi atau Kabel LAN) lalu coba lagi."
        echo "=========================================================="
        exit 1
    fi
    echo "Instalasi tshark selesai."
fi

PCAP_FILE="results/network/qos_real.pcap"

echo "Menangkap paket TCP port 5000 (N3IWF) dari semua Pico..."
echo "Menggunakan tool: tshark"
echo "Tekan Ctrl+C untuk berhenti merekam."
echo "Menyimpan ke: $PCAP_FILE"

# Menggunakan interface 'any' untuk menangkap baik eth0, wlan0, maupun ipsec0
sudo tshark -i any -f "tcp port 5000" -w "$PCAP_FILE"
