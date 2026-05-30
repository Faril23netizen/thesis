#!/bin/bash
# capture_qos.sh
# Script for recording network traffic (QoS) using tshark.
# Captured data will be saved to results/network/qos_real.pcap
# Can be opened in Wireshark (Windows) for QoS analysis (Bandwidth, Jitter, Packet Loss).

mkdir -p results/network

echo "=========================================================="
echo "  [N3IWF QoS Monitor] Starting Wireshark Capture (tshark)"
echo "=========================================================="

# Check if tshark is installed
if ! command -v tshark &> /dev/null
then
    echo "tshark not found. Performing automatic installation..."
    echo "NOTE: Make sure your Raspberry Pi has an active INTERNET CONNECTION!"

    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y tshark

    # Verify the installation actually succeeded
    if ! command -v tshark &> /dev/null; then
        echo "=========================================================="
        echo "FATAL ERROR: Failed to download tshark!"
        echo "Cause: Your Raspberry Pi is not connected to the internet (DNS resolution failed)."
        echo "Solution: Connect your Raspberry Pi to the internet (via WiFi or LAN cable) and try again."
        echo "=========================================================="
        exit 1
    fi
    echo "tshark installation complete."
fi

PCAP_FILE="results/network/qos_real.pcap"

echo "Capturing TCP port 5000 (N3IWF) packets from all Picos..."
echo "Using tool: tshark"
echo "Press Ctrl+C to stop recording."
echo "Saving to: $PCAP_FILE"

# Using interface 'any' to capture traffic on eth0, wlan0, and ipsec0
sudo tshark -i any -f "tcp port 5000" -w "$PCAP_FILE"
