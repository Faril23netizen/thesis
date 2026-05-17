#!/usr/bin/env python3
"""
n3iwf_client.py - N3IWF Client for RPi5
========================================
N3IWF (Non-3GPP Interworking Function) client yang berjalan di RPi5.
Menghubungkan WiFi network ke 5G Core melalui IPsec tunnel.

Usage:
  # Setelah Callbox simulator jalan
  sudo python3 n3iwf/n3iwf_client.py
"""

import os
import sys
import time
import subprocess
import json
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
CALLBOX_IP = "10.42.0.1"  # Callbox IP
N3IWF_CLIENT_IP = "10.42.0.1"  # RPi5 IP
IPSEC_TUNNEL_IP_CALLBOX = "192.168.100.1"
IPSEC_TUNNEL_IP_N3IWF = "192.168.100.2"

LOG_FILE = "results/network/n3iwf_client.log"
STATUS_FILE = "results/network/n3iwf_status.json"

os.makedirs("results/network", exist_ok=True)


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] {msg}"
    print(log_msg)
    
    with open(LOG_FILE, "a") as f:
        f.write(log_msg + "\n")


# ── IPsec Setup ───────────────────────────────────────────────────────────────
def setup_ipsec_client():
    """Setup IPsec client configuration"""
    log("Setting up N3IWF IPsec client...")
    
    # Check strongSwan
    try:
        result = subprocess.run(["which", "ipsec"], capture_output=True, text=True)
        if result.returncode != 0:
            log("strongSwan not installed!", "ERROR")
            log("Install: sudo apt install strongswan strongswan-pki", "ERROR")
            return False
    except Exception as e:
        log(f"Error: {e}", "ERROR")
        return False
    
    # Wait for callbox config
    log("Waiting for callbox config...", "INFO")
    for i in range(10):
        if os.path.exists("/tmp/ipsec_callbox.conf"):
            break
        time.sleep(1)
    
    # Read callbox config if exists
    callbox_config = ""
    if os.path.exists("/tmp/ipsec_callbox.conf"):
        with open("/tmp/ipsec_callbox.conf", "r") as f:
            callbox_config = f.read()
        log("Found callbox config, will merge", "INFO")
    
    # IPsec config for N3IWF client (initiator)
    # NOTE: This will be merged with callbox config
    n3iwf_conn = f"""
conn n3iwf-callbox
    type=tunnel
    auto=start
    keyexchange=ikev2
    
    # N3IWF client (initiator) - initiate connection
    left={N3IWF_CLIENT_IP}
    leftsubnet={IPSEC_TUNNEL_IP_N3IWF}/32
    leftid=@n3iwf-client
    leftauth=psk
    
    # Callbox (responder) - same machine, use actual IP
    right={CALLBOX_IP}
    rightsubnet={IPSEC_TUNNEL_IP_CALLBOX}/32
    rightid=@callbox
    rightauth=psk
    
    # IKE/ESP parameters
    ike=aes256-sha256-modp2048!
    esp=aes256-sha256!
    
    # Keepalive
    dpdaction=restart
    dpddelay=30s
    dpdtimeout=120s
"""
    
    # Merge configs
    if callbox_config:
        # Extract config setup from callbox
        merged_config = callbox_config.rstrip() + "\n" + n3iwf_conn
    else:
        # No callbox config, use standalone
        merged_config = f"""
config setup
    charondebug="ike 2, knl 2, cfg 2, net 2"
    uniqueids=never

{n3iwf_conn}
"""
    
    ipsec_secrets = f"""
# PSK for N3IWF tunnel
@n3iwf-client @callbox : PSK "aquaculture_n3iwf_2026_secret_key"
"""
    
    try:
        # Write merged config
        with open("/tmp/ipsec_merged.conf", "w") as f:
            f.write(merged_config)
        
        with open("/tmp/ipsec_merged.secrets", "w") as f:
            f.write(ipsec_secrets)
        
        # Backup existing config
        if os.path.exists("/etc/ipsec.conf"):
            subprocess.run(["sudo", "cp", "/etc/ipsec.conf", "/etc/ipsec.conf.backup"], check=False)
        
        # Install merged config
        subprocess.run(["sudo", "cp", "/tmp/ipsec_merged.conf", "/etc/ipsec.conf"], check=True)
        subprocess.run(["sudo", "cp", "/tmp/ipsec_merged.secrets", "/etc/ipsec.secrets"], check=True)
        subprocess.run(["sudo", "chmod", "600", "/etc/ipsec.secrets"], check=True)
        
        log("IPsec merged config installed successfully", "INFO")
        log("Config includes both callbox and N3IWF connections", "INFO")
        return True
        
    except Exception as e:
        log(f"Error installing IPsec config: {e}", "ERROR")
        return False


def start_ipsec():
    """Start IPsec service"""
    log("Starting IPsec service...")
    
    try:
        # Stop existing
        subprocess.run(["sudo", "ipsec", "stop"], capture_output=True)
        time.sleep(2)
        
        # Start
        result = subprocess.run(["sudo", "ipsec", "start"], capture_output=True, text=True)
        if result.returncode == 0:
            log("IPsec service started", "INFO")
            time.sleep(3)
            
            # Check status
            result = subprocess.run(["sudo", "ipsec", "statusall"], capture_output=True, text=True)
            if "ESTABLISHED" in result.stdout:
                log("IPsec tunnel ESTABLISHED!", "INFO")
                return True
            else:
                log("IPsec tunnel not established yet, waiting...", "WARN")
                return False
        else:
            log(f"Failed to start IPsec: {result.stderr}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Error starting IPsec: {e}", "ERROR")
        return False


def check_tunnel_status():
    """Check IPsec tunnel status"""
    try:
        result = subprocess.run(
            ["sudo", "ipsec", "statusall"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        status = {
            "timestamp": datetime.now().isoformat(),
            "established": "ESTABLISHED" in result.stdout,
            "output": result.stdout
        }
        
        # Save status
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
        
        return status["established"]
        
    except Exception as e:
        log(f"Error checking tunnel: {e}", "ERROR")
        return False


def ping_callbox():
    """Ping Callbox through tunnel"""
    try:
        result = subprocess.run(
            ["ping", "-c", "3", "-W", "2", IPSEC_TUNNEL_IP_CALLBOX],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Parse latency
            for line in result.stdout.split("\n"):
                if "avg" in line or "rtt" in line:
                    log(f"Ping to Callbox: {line.strip()}", "INFO")
            return True
        else:
            log("Ping to Callbox failed", "WARN")
            return False
            
    except Exception as e:
        log(f"Error pinging Callbox: {e}", "ERROR")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log("="*70)
    log("N3IWF Client Starting...")
    log("="*70)
    log(f"Client IP: {N3IWF_CLIENT_IP}")
    log(f"Callbox IP: {CALLBOX_IP}")
    log(f"Tunnel IP (N3IWF): {IPSEC_TUNNEL_IP_N3IWF}")
    log(f"Tunnel IP (Callbox): {IPSEC_TUNNEL_IP_CALLBOX}")
    log("="*70)
    
    # Setup IPsec
    if not setup_ipsec_client():
        log("Failed to setup IPsec client", "ERROR")
        return 1
    
    # Start IPsec
    if not start_ipsec():
        log("Failed to start IPsec", "ERROR")
        log("Retrying in 5 seconds...", "WARN")
        time.sleep(5)
        start_ipsec()
    
    # Monitor tunnel
    log("Monitoring IPsec tunnel...")
    try:
        while True:
            if check_tunnel_status():
                log("✅ Tunnel ESTABLISHED", "INFO")
                
                # Test connectivity
                if ping_callbox():
                    log("✅ Connectivity OK", "INFO")
                else:
                    log("⚠️  Connectivity issue", "WARN")
            else:
                log("❌ Tunnel DOWN", "ERROR")
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        log("Shutting down N3IWF client...", "INFO")
        return 0


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("⚠️  This script requires root privileges")
        print("   Run: sudo python3 n3iwf/n3iwf_client.py")
        sys.exit(1)
    
    sys.exit(main())
