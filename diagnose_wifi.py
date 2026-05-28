#!/usr/bin/env python3
"""
WiFi Hotspot Diagnostics — N3IWF Aquaculture
Monitors why a device fails to join the hotspot.
Run on RPi: sudo python3 diagnose_wifi.py
"""

import subprocess
import time
import sys
import json
from datetime import datetime

IFACE = "wlan0"

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception as e:
        return f"[ERR: {e}]"

def get_stations():
    """Returns dict of {MAC: info} currently associated."""
    out = run(f"iw dev {IFACE} station dump")
    stations = {}
    current_mac = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Station"):
            current_mac = line.split()[1]
            stations[current_mac] = {}
        elif current_mac and ":" in line:
            key, _, val = line.partition(":")
            stations[current_mac][key.strip()] = val.strip()
    return stations

def get_dhcp_leases():
    """Returns list of DHCP leases from NetworkManager dnsmasq."""
    paths = [
        "/var/lib/NetworkManager/dnsmasq-wlan0.leases",
        "/var/lib/misc/dnsmasq.leases",
        "/tmp/dnsmasq.leases"
    ]
    for path in paths:
        out = run(f"cat {path} 2>/dev/null")
        if out and "[ERR" not in out:
            leases = []
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    leases.append({
                        "expiry": parts[0],
                        "mac": parts[1],
                        "ip": parts[2],
                        "hostname": parts[3]
                    })
            return leases
    return []

def get_hostapd_events():
    """Grab recent WiFi association events from journal."""
    out = run("journalctl -u NetworkManager --since '2 minutes ago' --no-pager -q 2>/dev/null | grep -i 'assoc\\|auth\\|join\\|station\\|client\\|connect\\|reject\\|fail' | tail -20")
    return out

def get_nm_events():
    """Recent NetworkManager WiFi events."""
    out = run("journalctl -u NetworkManager --since '1 minute ago' --no-pager -q 2>/dev/null | tail -15")
    return out

def check_hotspot_config():
    """Check hotspot SSID, security, channel."""
    ssid = run("nmcli con show N3IWF_AQUA | grep '802-11-wireless.ssid'")
    security = run("nmcli con show N3IWF_AQUA | grep 'wifi-sec.key-mgmt'")
    band = run("nmcli con show N3IWF_AQUA | grep '802-11-wireless.band'")
    channel = run("nmcli con show N3IWF_AQUA | grep '802-11-wireless.channel'")
    ip = run("nmcli con show N3IWF_AQUA | grep 'ipv4.addresses'")
    max_clients = run("nmcli con show N3IWF_AQUA | grep 'ap-max'")
    
    return {
        "ssid": ssid,
        "security": security,
        "band": band,
        "channel": channel,
        "ip_range": ip,
        "max_clients": max_clients
    }

def main():
    print("=" * 60)
    print(" N3IWF WiFi Hotspot Diagnostics")
    print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # --- Hotspot config ---
    print("\n[1] Hotspot Configuration:")
    cfg = check_hotspot_config()
    for k, v in cfg.items():
        print(f"    {k}: {v}")

    # --- Current stations ---
    print("\n[2] Currently Associated Stations:")
    stations = get_stations()
    if not stations:
        print("    NONE — no devices connected!")
    for mac, info in stations.items():
        signal = info.get("signal", "?")
        rx = info.get("rx bytes", "?")
        tx = info.get("tx bytes", "?")
        print(f"    MAC: {mac} | Signal: {signal} | RX: {rx} | TX: {tx}")

    # --- DHCP leases ---
    print("\n[3] DHCP Leases (known devices):")
    leases = get_dhcp_leases()
    if not leases:
        print("    None found (check with: sudo cat /var/lib/NetworkManager/dnsmasq-wlan0.leases)")
    for l in leases:
        print(f"    IP: {l['ip']} | MAC: {l['mac']} | Name: {l['hostname']}")

    # --- Auth failures ---
    print("\n[4] Recent Auth/Association Events from Journal:")
    events = get_hostapd_events()
    print(events if events else "    (none found — hotspot may not log at this level)")

    print("\n[5] NetworkManager Recent Events:")
    nm = get_nm_events()
    print(nm if nm else "    (none)")

    # --- Monitoring loop ---
    print("\n" + "=" * 60)
    print(" Live Monitor: watching for new device connections...")
    print(" Press Ctrl+C to stop.")
    print("=" * 60)
    
    known_macs = set(get_stations().keys())
    
    try:
        while True:
            time.sleep(2)
            current = get_stations()
            current_macs = set(current.keys())

            # New device joined
            for mac in current_macs - known_macs:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{ts}] ✅ NEW DEVICE JOINED: {mac}")
                print(f"    Signal: {current[mac].get('signal', '?')}")
                leases = get_dhcp_leases()
                for l in leases:
                    if l['mac'].lower() == mac.lower():
                        print(f"    IP: {l['ip']} | Hostname: {l['hostname']}")

            # Device left
            for mac in known_macs - current_macs:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{ts}] ❌ DEVICE LEFT: {mac}")

            known_macs = current_macs

            # Every 10s print summary
            if int(time.time()) % 10 == 0:
                ts = datetime.now().strftime("%H:%M:%S")
                sys.stdout.write(f"\r[{ts}] Connected: {len(current_macs)} station(s): {', '.join(current_macs) or 'NONE'}    ")
                sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\nDiagnostics stopped.")

if __name__ == "__main__":
    if subprocess.run("which iw", shell=True, capture_output=True).returncode != 0:
        print("ERROR: 'iw' not found. Install with: sudo apt install iw")
        sys.exit(1)
    main()
