#!/bin/bash
# capture_qos.sh
# Skrip untuk merekam lalu lintas jaringan (QoS) menggunakan tshark.
# Hasil rekaman akan disimpan di results/network/qos_real.pcap
# Dapat dibuka di Wireshark (Windows) untuk analisis QoS (Bandwidth, Jitter, Packet Loss).

mkdir -p results/network

echo "=========================================================="
echo "  [N3IWF QoS Monitor] Memulai Perekaman Wireshark (tshark)"
echo "=========================================================="

# Cek apakah tshark atau tcpdump tersedia
CAPTURE_TOOL=""
if command -v tshark &> /dev/null; then
    CAPTURE_TOOL="tshark"
elif command -v tcpdump &> /dev/null; then
    CAPTURE_TOOL="tcpdump"
else
    echo "tshark dan tcpdump tidak ditemukan. Mencoba instalasi tcpdump..."
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y tcpdump
    if command -v tcpdump &> /dev/null; then
        CAPTURE_TOOL="tcpdump"
    else
        echo "ERROR: Gagal menginstall tcpdump. Pastikan Raspberry Pi terhubung ke internet."
        exit 1
    fi
fi

PCAP_FILE="results/network/qos_real.pcap"

echo "Menangkap paket TCP port 5000 (N3IWF) dari semua Pico..."
echo "Menggunakan tool: $CAPTURE_TOOL"
echo "Tekan Ctrl+C untuk berhenti merekam."
echo "Menyimpan ke: $PCAP_FILE"

# Menggunakan interface 'any' untuk menangkap baik eth0, wlan0, maupun ipsec0
if [ "$CAPTURE_TOOL" == "tshark" ]; then
    sudo tshark -i any -f "tcp port 5000" -w "$PCAP_FILE"
else
    sudo tcpdump -i any "tcp port 5000" -w "$PCAP_FILE"
fi
