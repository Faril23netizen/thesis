#!/bin/bash
echo "Hotspot watchdog started..."
while true; do
    sleep 15
    CLIENTS=$(iw dev wlan0 station dump 2>/dev/null | grep -c "Station")
    if [ "$CLIENTS" -eq 0 ]; then
        echo "$(date): No clients — restarting hotspot..."
        nmcli connection down N3IWF_AQUA 2>/dev/null
        sleep 2
        nmcli connection up N3IWF_AQUA
        echo "$(date): Hotspot restarted."
    fi
done
