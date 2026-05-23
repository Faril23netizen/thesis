#!/usr/bin/env python3
"""
Network Diagnostic Tool - Pico WH to RPi5 Connection
=====================================================
Diagnose why Pico WH cannot connect to RPi5

Usage:
    python3 diagnostic_network.py
"""

import socket
import subprocess
import sys
import time
import os
from datetime import datetime

def log(msg, level="INFO"):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def check_network_interface():
    """Check if network interfaces are up"""
    log("=" * 70)
    log("STEP 1: Checking Network Interfaces")
    log("=" * 70)
    
    try:
        result = subprocess.run(["ip", "addr", "show"], 
                              capture_output=True, text=True, timeout=5)
        print(result.stdout)
        
        # Check for wlan0 or eth0
        if "wlan0" in result.stdout or "eth0" in result.stdout:
            log("✅ Network interface found", "OK")
            return True
        else:
            log("❌ No network interface found", "ERROR")
            return False
    except Exception as e:
        log(f"❌ Error checking interfaces: {e}", "ERROR")
        return False

def check_wifi_hotspot():
    """Check if WiFi hotspot N3IWF_AQUA is active"""
    log("=" * 70)
    log("STEP 2: Checking WiFi Hotspot (N3IWF_AQUA)")
    log("=" * 70)
    
    try:
        # First check NetworkManager (modern approach)
        result = subprocess.run(["nmcli", "connection", "show", "--active"], 
                              capture_output=True, text=True)
        if "N3IWF_AQUA" in result.stdout and "wlan0" in result.stdout:
            log("✅ N3IWF_AQUA hotspot is active (NetworkManager)", "OK")
            return True
        
        # Fallback: check hostapd (legacy approach)
        result = subprocess.run(["systemctl", "is-active", "hostapd"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            log("✅ hostapd service is active", "OK")
            
            # Check if dnsmasq is running
            result = subprocess.run(["systemctl", "is-active", "dnsmasq"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                log("✅ dnsmasq service is active", "OK")
            else:
                log("❌ dnsmasq service is NOT active", "ERROR")
                log("   Run: sudo systemctl start dnsmasq", "HINT")
                return False
            
            # Check hostapd config
            if os.path.exists("/etc/hostapd/hostapd.conf"):
                with open("/etc/hostapd/hostapd.conf", "r") as f:
                    config = f.read()
                    if "ssid=N3IWF_AQUA" in config:
                        log("✅ SSID configured as N3IWF_AQUA", "OK")
                    else:
                        log("❌ SSID is NOT N3IWF_AQUA", "ERROR")
                        return False
                    
                    if "wpa_passphrase=skripsi2026" in config:
                        log("✅ Password configured correctly", "OK")
                    else:
                        log("⚠️  Password might be different", "WARN")
            
            return True
        
        # Neither method found active hotspot
        log("❌ WiFi hotspot is NOT active", "ERROR")
        log("   NetworkManager: sudo bash fix_hotspot_nm.sh", "HINT")
        log("   OR hostapd: sudo systemctl start hostapd", "HINT")
        return False
        
    except Exception as e:
        log(f"❌ Error checking hotspot: {e}", "ERROR")
        return False

def check_ip_address():
    """Check if RPi has IP 10.42.0.1"""
    log("=" * 70)
    log("STEP 3: Checking IP Address (10.42.0.1)")
    log("=" * 70)
    
    try:
        result = subprocess.run(["ip", "addr", "show", "wlan0"], 
                              capture_output=True, text=True, timeout=5)
        
        if "10.42.0.1" in result.stdout:
            log("✅ RPi5 has IP 10.42.0.1 on wlan0", "OK")
            return True
        else:
            log("❌ RPi5 does NOT have IP 10.42.0.1", "ERROR")
            log("   Current wlan0 config:", "INFO")
            print(result.stdout)
            log("   Run: sudo ip addr add 10.42.0.1/24 dev wlan0", "HINT")
            return False
    except Exception as e:
        log(f"❌ Error checking IP: {e}", "ERROR")
        return False

def check_firewall():
    """Check if firewall is blocking port 5000"""
    log("=" * 70)
    log("STEP 4: Checking Firewall (Port 5000)")
    log("=" * 70)
    
    try:
        # Check if ufw is active
        result = subprocess.run(["sudo", "ufw", "status"], 
                              capture_output=True, text=True)
        
        if "Status: active" in result.stdout:
            log("⚠️  UFW firewall is active", "WARN")
            if "5000" in result.stdout and "ALLOW" in result.stdout:
                log("✅ Port 5000 is allowed", "OK")
            else:
                log("❌ Port 5000 is NOT allowed", "ERROR")
                log("   Run: sudo ufw allow 5000/tcp", "HINT")
                return False
        else:
            log("✅ UFW firewall is inactive", "OK")
        
        # Check iptables
        result = subprocess.run(["sudo", "iptables", "-L", "-n"], 
                              capture_output=True, text=True)
        if "DROP" in result.stdout or "REJECT" in result.stdout:
            log("⚠️  iptables has DROP/REJECT rules", "WARN")
            print(result.stdout)
        else:
            log("✅ No blocking iptables rules", "OK")
        
        return True
    except Exception as e:
        log(f"⚠️  Could not check firewall: {e}", "WARN")
        return True  # Don't fail if we can't check

def check_port_listening():
    """Check if port 5000 is listening"""
    log("=" * 70)
    log("STEP 5: Checking if Port 5000 is Listening")
    log("=" * 70)
    
    try:
        result = subprocess.run(["ss", "-tlnp"], 
                              capture_output=True, text=True, timeout=5)
        
        if ":5000" in result.stdout:
            log("✅ Port 5000 is listening", "OK")
            # Show what's listening
            for line in result.stdout.split("\n"):
                if ":5000" in line:
                    log(f"   {line.strip()}", "INFO")
            return True
        else:
            log("❌ Port 5000 is NOT listening", "ERROR")
            log("   No service is listening on port 5000", "HINT")
            log("   Start the server: python3 main/real/run_real.py", "HINT")
            return False
    except Exception as e:
        log(f"❌ Error checking port: {e}", "ERROR")
        return False

def test_tcp_server():
    """Test if we can bind to port 5000"""
    log("=" * 70)
    log("STEP 6: Testing TCP Server on Port 5000")
    log("=" * 70)
    
    try:
        # Try to create a test server
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test_sock.bind(("0.0.0.0", 5000))
        test_sock.listen(1)
        test_sock.settimeout(5)
        
        log("✅ Successfully bound to 0.0.0.0:5000", "OK")
        log("   Waiting 5 seconds for Pico connection...", "INFO")
        
        try:
            conn, addr = test_sock.accept()
            log(f"✅ Connection received from {addr[0]}:{addr[1]}", "OK")
            log("   This is likely your Pico WH!", "SUCCESS")
            
            # Try to receive data
            conn.settimeout(2)
            data = conn.recv(1024)
            if data:
                log(f"   Received: {data.decode('utf-8', errors='ignore')}", "INFO")
            
            conn.close()
            test_sock.close()
            return True
        except socket.timeout:
            log("⚠️  No connection received in 5 seconds", "WARN")
            log("   Pico might not be trying to connect", "HINT")
            test_sock.close()
            return False
            
    except OSError as e:
        if e.errno == 98:  # Address already in use
            log("⚠️  Port 5000 is already in use", "WARN")
            log("   Another service is using this port", "INFO")
            log("   Check: sudo ss -tlnp | grep 5000", "HINT")
        else:
            log(f"❌ Error binding to port: {e}", "ERROR")
        return False
    except Exception as e:
        log(f"❌ Error testing server: {e}", "ERROR")
        return False

def check_connected_devices():
    """Check if any device is connected to WiFi hotspot"""
    log("=" * 70)
    log("STEP 7: Checking Connected WiFi Devices")
    log("=" * 70)
    
    try:
        # Check ARP table for devices on 10.42.0.x
        result = subprocess.run(["arp", "-n"], 
                              capture_output=True, text=True, timeout=5)
        
        devices = []
        for line in result.stdout.split("\n"):
            if "10.42.0." in line and "10.42.0.1" not in line:
                devices.append(line.strip())
        
        if devices:
            log(f"✅ Found {len(devices)} device(s) on network:", "OK")
            for dev in devices:
                log(f"   {dev}", "INFO")
            return True
        else:
            log("❌ No devices found on 10.42.0.x network", "ERROR")
            log("   Pico WH has not connected to WiFi yet", "HINT")
            log("   Check Pico serial output for WiFi errors", "HINT")
            return False
    except Exception as e:
        log(f"❌ Error checking devices: {e}", "ERROR")
        return False

def ping_test():
    """Try to ping common Pico IP"""
    log("=" * 70)
    log("STEP 8: Ping Test to Pico (if known)")
    log("=" * 70)
    
    # Try common DHCP IPs
    test_ips = ["10.42.0.2", "10.42.0.10", "10.42.0.100"]
    
    for ip in test_ips:
        try:
            result = subprocess.run(["ping", "-c", "1", "-W", "1", ip], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                log(f"✅ Pico WH found at {ip}", "SUCCESS")
                return True
        except:
            pass
    
    log("⚠️  Could not ping Pico on common IPs", "WARN")
    log("   Pico might have different IP or not connected", "HINT")
    return False

def main():
    """Run all diagnostic checks"""
    print("\n")
    log("╔═══════════════════════════════════════════════════════════════════╗")
    log("║   Pico WH to RPi5 Connection Diagnostic Tool                     ║")
    log("╚═══════════════════════════════════════════════════════════════════╝")
    print("\n")
    
    results = {
        "Network Interface": check_network_interface(),
        "WiFi Hotspot": check_wifi_hotspot(),
        "IP Address": check_ip_address(),
        "Firewall": check_firewall(),
        "Port Listening": check_port_listening(),
        "Connected Devices": check_connected_devices(),
        "Ping Test": ping_test(),
    }
    
    # Only test TCP if port is not already in use
    if not results["Port Listening"]:
        results["TCP Server Test"] = test_tcp_server()
    
    # Summary
    print("\n")
    log("=" * 70)
    log("DIAGNOSTIC SUMMARY")
    log("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        log(f"{check:.<50} {status}")
    
    print("\n")
    log(f"Result: {passed}/{total} checks passed")
    
    if passed == total:
        log("🎉 All checks passed! Connection should work.", "SUCCESS")
    else:
        log("⚠️  Some checks failed. Fix the issues above.", "WARN")
        log("", "")
        log("Common fixes:", "HINT")
        log("  1. Start WiFi hotspot: sudo systemctl start hostapd dnsmasq", "HINT")
        log("  2. Set IP address: sudo ip addr add 10.42.0.1/24 dev wlan0", "HINT")
        log("  3. Allow firewall: sudo ufw allow 5000/tcp", "HINT")
        log("  4. Start server: python3 main/real/run_real.py", "HINT")
        log("  5. Check Pico serial output for WiFi connection errors", "HINT")
    
    print("\n")
    return 0 if passed == total else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n")
        log("Diagnostic interrupted by user", "INFO")
        sys.exit(1)
