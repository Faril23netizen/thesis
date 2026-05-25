#!/usr/bin/env python3
"""
callbox_simulator.py - 5G Callbox Simulator
============================================
Simulasi Callbox 5G untuk testing N3IWF deployment.

Fitur:
- Simulasi 5G Core Network (AMF, SMF, UPF)
- IPsec responder untuk N3IWF tunnel
- Network latency simulation
- Packet loss simulation
- Bandwidth throttling
- Monitoring & logging

Usage:
  # Terminal 1: Jalankan Callbox Simulator
  sudo python3 n3iwf/callbox_simulator.py
  
  # Terminal 2: Jalankan N3IWF Client (RPi5)
  sudo python3 n3iwf/n3iwf_client.py
  
  # Terminal 3: Jalankan Server
  python3 n3iwf/server.py
"""

import os
import sys
import time
import json
import socket
import threading
import subprocess
import random
from datetime import datetime
from collections import deque

# ── Configuration ─────────────────────────────────────────────────────────────
CALLBOX_IP = "10.42.0.1"  # RPi5 IP (acting as Callbox)
N3IWF_CLIENT_IP = "10.42.0.1"  # Same machine for simulation
IPSEC_TUNNEL_IP = "192.168.100.1"  # Virtual tunnel IP for Callbox
N3IWF_TUNNEL_IP = "192.168.100.2"  # Virtual tunnel IP for N3IWF client

# Network simulation parameters
BASE_LATENCY_MS = 10  # Base latency (ms)
JITTER_MS = 5  # Random jitter (±ms)
PACKET_LOSS_RATE = 0.01  # 1% packet loss
BANDWIDTH_MBPS = 100  # Simulated bandwidth

# Monitoring
STATS_FILE = "results/network/callbox_stats.json"
TIMELINE_FILE = "results/network/network_timeline.csv"
LOG_FILE = "results/network/callbox.log"

os.makedirs("results/network", exist_ok=True)

# ── Global State ──────────────────────────────────────────────────────────────
stats = {
    "uptime": 0,
    "packets_received": 0,
    "packets_sent": 0,
    "packets_dropped": 0,
    "active_tunnels": 0,
    "avg_latency_ms": 0,
    "jitter_ms": 0,
    "current_bandwidth_mbps": BANDWIDTH_MBPS,
    "ipsec_status": "DOWN",
    "amf_status": "RUNNING",
    "smf_status": "RUNNING",
    "upf_status": "RUNNING",
    "nodes": {
        "Pico_1_Main": {"latency_ms": 0, "jitter_ms": 0, "bandwidth_mbps": 0},
        "Pico_2_Dummy": {"latency_ms": 0, "jitter_ms": 0, "bandwidth_mbps": 0},
        "Pico_3_Dummy": {"latency_ms": 0, "jitter_ms": 0, "bandwidth_mbps": 0}
    }
}

node_latency_history = {
    "Pico_1_Main": [],
    "Pico_2_Dummy": [],
    "Pico_3_Dummy": []
}
stats_lock = threading.Lock()


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] {msg}"
    print(log_msg)
    
    with open(LOG_FILE, "a") as f:
        f.write(log_msg + "\n")


# ── Network Simulation ────────────────────────────────────────────────────────
def simulate_network_delay():
    """Simulate network latency with jitter"""
    latency = BASE_LATENCY_MS + random.uniform(-JITTER_MS, JITTER_MS)
    time.sleep(latency / 1000.0)  # Convert to seconds
    return latency


def should_drop_packet():
    """Simulate packet loss"""
    return random.random() < PACKET_LOSS_RATE


# ── IPsec Tunnel Simulator ────────────────────────────────────────────────────
def setup_ipsec_tunnel():
    """Setup IPsec tunnel using strongSwan"""
    log("Setting up IPsec tunnel (Callbox side)...")
    
    # Check if strongSwan is installed
    try:
        result = subprocess.run(["which", "ipsec"], capture_output=True, text=True)
        if result.returncode != 0:
            log("strongSwan not installed. Installing...", "WARN")
            log("Run: sudo apt install strongswan strongswan-pki", "WARN")
            return False
    except Exception as e:
        log(f"Error checking strongSwan: {e}", "ERROR")
        return False
    
    # Create IPsec config for Callbox (responder)
    # NOTE: This will be merged with N3IWF client config
    ipsec_conf = f"""
config setup
    charondebug="ike 2, knl 2, cfg 2, net 2"
    uniqueids=never

conn callbox-n3iwf
    type=tunnel
    auto=add
    keyexchange=ikev2
    
    # Callbox (responder) - listen for connections
    left={CALLBOX_IP}
    leftsubnet={IPSEC_TUNNEL_IP}/32
    leftid=@callbox
    leftauth=psk
    
    # N3IWF client (initiator)
    right={CALLBOX_IP}
    rightsubnet={N3IWF_TUNNEL_IP}/32
    rightid=@n3iwf-client
    rightauth=psk
    
    # IKE/ESP parameters
    ike=aes256-sha256-modp2048!
    esp=aes256-sha256!
    
    # Keepalive
    dpdaction=restart
    dpddelay=30s
    dpdtimeout=120s
"""
    
    ipsec_secrets = f"""
# PSK for N3IWF tunnel
@callbox @n3iwf-client : PSK "aquaculture_n3iwf_2026_secret_key"
"""
    
    try:
        # Write config files to /tmp (will be merged later)
        with open("/tmp/ipsec_callbox.conf", "w") as f:
            f.write(ipsec_conf)
        
        with open("/tmp/ipsec_callbox.secrets", "w") as f:
            f.write(ipsec_secrets)
        
        log("IPsec config files created in /tmp", "INFO")
        log("Config will be merged with N3IWF client config", "INFO")
        
        return True
        
    except Exception as e:
        log(f"Error creating IPsec config: {e}", "ERROR")
        return False


def check_ipsec_status():
    """Check IPsec tunnel status"""
    try:
        result = subprocess.run(
            ["sudo", "ipsec", "statusall"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if "ESTABLISHED" in result.stdout:
            with stats_lock:
                stats["ipsec_status"] = "ESTABLISHED"
                stats["active_tunnels"] = result.stdout.count("ESTABLISHED")
            return True
        else:
            with stats_lock:
                stats["ipsec_status"] = "DOWN"
                stats["active_tunnels"] = 0
            return False
            
    except Exception as e:
        log(f"Error checking IPsec status: {e}", "ERROR")
        with stats_lock:
            stats["ipsec_status"] = "ERROR"
        return False


# ── 5G Core Components Simulator ──────────────────────────────────────────────
class AMFSimulator:
    """Access and Mobility Management Function"""
    def __init__(self):
        self.registered_ues = {}
        self.status = "RUNNING"
    
    def register_ue(self, ue_id):
        """Register UE (User Equipment)"""
        self.registered_ues[ue_id] = {
            "registered_at": time.time(),
            "status": "REGISTERED",
            "ip": N3IWF_TUNNEL_IP
        }
        log(f"[AMF] UE registered: {ue_id}", "INFO")
        return True
    
    def deregister_ue(self, ue_id):
        """Deregister UE"""
        if ue_id in self.registered_ues:
            del self.registered_ues[ue_id]
            log(f"[AMF] UE deregistered: {ue_id}", "INFO")
        return True


class SMFSimulator:
    """Session Management Function"""
    def __init__(self):
        self.sessions = {}
        self.status = "RUNNING"
    
    def create_session(self, ue_id, session_id):
        """Create PDU session"""
        self.sessions[session_id] = {
            "ue_id": ue_id,
            "created_at": time.time(),
            "status": "ACTIVE",
            "qos": "QoS-1",  # Default QoS
            "bandwidth_mbps": BANDWIDTH_MBPS
        }
        log(f"[SMF] Session created: {session_id} for UE {ue_id}", "INFO")
        return True
    
    def delete_session(self, session_id):
        """Delete PDU session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            log(f"[SMF] Session deleted: {session_id}", "INFO")
        return True


class UPFSimulator:
    """User Plane Function"""
    def __init__(self):
        self.packet_count = 0
        self.byte_count = 0
        self.status = "RUNNING"
    
    def forward_packet(self, packet_size):
        """Forward packet through UPF"""
        # Simulate network delay
        latency = simulate_network_delay()
        
        # Simulate packet loss
        if should_drop_packet():
            with stats_lock:
                stats["packets_dropped"] += 1
            return False, latency
        
        # Forward packet
        self.packet_count += 1
        self.byte_count += packet_size
        
        with stats_lock:
            stats["packets_sent"] += 1
            latency_history.append(latency)
            if latency_history:
                stats["avg_latency_ms"] = sum(latency_history) / len(latency_history)
        
        return True, latency


# ── Main Callbox Simulator ────────────────────────────────────────────────────
class CallboxSimulator:
    def __init__(self):
        self.amf = AMFSimulator()
        self.smf = SMFSimulator()
        self.upf = UPFSimulator()
        self.running = False
        self.start_time = time.time()
    
    def start(self):
        """Start Callbox simulator"""
        self.running = True
        log("="*70, "INFO")
        log("5G Callbox Simulator Started", "INFO")
        log("="*70, "INFO")
        log(f"Callbox IP: {CALLBOX_IP}", "INFO")
        log(f"IPsec Tunnel IP: {IPSEC_TUNNEL_IP}", "INFO")
        log(f"Base Latency: {BASE_LATENCY_MS}ms ± {JITTER_MS}ms", "INFO")
        log(f"Packet Loss Rate: {PACKET_LOSS_RATE*100}%", "INFO")
        log(f"Bandwidth: {BANDWIDTH_MBPS} Mbps", "INFO")
        log("="*70, "INFO")
        
        # Setup IPsec
        setup_ipsec_tunnel()
        
        # Register default UE (N3IWF client)
        self.amf.register_ue("n3iwf-client")
        self.smf.create_session("n3iwf-client", "session-001")
        
        # Start monitoring threads
        threading.Thread(target=self._monitor_ipsec, daemon=True).start()
        threading.Thread(target=self._update_stats, daemon=True).start()
        threading.Thread(target=self._save_stats, daemon=True).start()
        
        log("Callbox simulator ready. Waiting for N3IWF client...", "INFO")
        
        # Keep running
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            log("Shutting down Callbox simulator...", "INFO")
            self.stop()
    
    def stop(self):
        """Stop Callbox simulator"""
        self.running = False
        log("Callbox simulator stopped", "INFO")
    
    def _monitor_ipsec(self):
        """Monitor IPsec tunnel status"""
        while self.running:
            check_ipsec_status()
            time.sleep(5)
    
    def _update_stats(self):
        """Update statistics"""
        while self.running:
            with stats_lock:
                stats["uptime"] = int(time.time() - self.start_time)
                stats["amf_status"] = self.amf.status
                stats["smf_status"] = self.smf.status
                stats["upf_status"] = self.upf.status
                
                stats["amf_ues"] = len(self.amf.registered_ues)
                stats["smf_sessions"] = len(self.smf.sessions)
                stats["upf_packets"] = self.upf.packet_count
                
                # Simulate network traffic if IPsec is established
                if stats["ipsec_status"] == "ESTABLISHED":
                    # Simulate latency (10-15ms with jitter)
                    current_lat = BASE_LATENCY_MS + random.uniform(-JITTER_MS, JITTER_MS)
                    
                    # Simulate packet traffic (increase over time)
                    packets_per_second = 10  # Simulate 10 packets/sec
                    stats["packets_sent"] += packets_per_second
                    stats["packets_received"] += packets_per_second
                    self.upf.packet_count += packets_per_second
                    
                    # Simulate packet loss (1%)
                    if random.random() < PACKET_LOSS_RATE:
                        stats["packets_dropped"] += 1
                    
                    # Update per-node latency and jitter
                    total_bw = 0.0
                    node_configs = {
                        "Pico_1_Main":  {"base_lat": 12, "bw_base": 35.0},
                        "Pico_2_Dummy": {"base_lat": 15, "bw_base": 30.0},
                        "Pico_3_Dummy": {"base_lat": 18, "bw_base": 35.0}
                    }

                    for node_id, cfg in node_configs.items():
                        # Generate node-specific metrics
                        n_lat = cfg["base_lat"] + random.uniform(-JITTER_MS, JITTER_MS)
                        n_bw = cfg["bw_base"] + random.uniform(-5.0, 5.0)
                        total_bw += n_bw
                        
                        history = node_latency_history[node_id]
                        history.append(n_lat)
                        if len(history) > 20:
                            history.pop(0)
                            
                        avg_lat = sum(history) / len(history) if len(history) > 0 else 0
                        
                        if len(history) > 1:
                            diffs = [abs(history[i] - history[i-1]) for i in range(1, len(history))]
                            avg_jit = sum(diffs) / len(diffs)
                        else:
                            avg_jit = 0.0
                            
                        stats["nodes"][node_id]["latency_ms"] = round(avg_lat, 1)
                        stats["nodes"][node_id]["jitter_ms"] = round(avg_jit, 2)
                        stats["nodes"][node_id]["bandwidth_mbps"] = round(n_bw, 1)
                    
                    # Update global averages for fallback
                    stats["avg_latency_ms"] = round(sum([stats["nodes"][n]["latency_ms"] for n in node_configs]) / 3, 1)
                    stats["jitter_ms"] = round(sum([stats["nodes"][n]["jitter_ms"] for n in node_configs]) / 3, 2)
                    stats["current_bandwidth_mbps"] = round(total_bw, 1)
            
            time.sleep(1)
    
    def _save_stats(self):
        """Save statistics to file"""
        log(f"Stats saver started, will save to {STATS_FILE}", "INFO")
        
        # Initialize CSV
        os.makedirs(os.path.dirname(TIMELINE_FILE), exist_ok=True)
        if not os.path.exists(TIMELINE_FILE):
            with open(TIMELINE_FILE, "w") as f:
                f.write("timestamp,uptime,avg_latency_ms,jitter_ms,packets_dropped,current_bandwidth_mbps\n")
                
        while self.running:
            try:
                with stats_lock:
                    stats_copy = stats.copy()
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
                
                with open(STATS_FILE, "w") as f:
                    json.dump(stats_copy, f, indent=2)
                    
                # Append to timeline CSV
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(TIMELINE_FILE, "a") as f:
                    f.write(f"{timestamp},{stats_copy['uptime']},{stats_copy['avg_latency_ms']:.2f},{stats_copy['jitter_ms']:.2f},{stats_copy['packets_dropped']},{stats_copy['current_bandwidth_mbps']}\n")
                
                log(f"Stats saved: uptime={stats_copy['uptime']}s, ipsec={stats_copy['ipsec_status']}", "DEBUG")
                
            except Exception as e:
                log(f"Error saving stats: {e}", "ERROR")
            
            time.sleep(5)


# ── CLI Interface ─────────────────────────────────────────────────────────────
def print_status():
    """Print current status"""
    with stats_lock:
        s = stats.copy()
    
    print("\n" + "="*70)
    print("  5G CALLBOX SIMULATOR STATUS")
    print("="*70)
    print(f"  Uptime:           {s['uptime']}s")
    print(f"  IPsec Status:     {s['ipsec_status']}")
    print(f"  Active Tunnels:   {s['active_tunnels']}")
    print()
    print(f"  AMF Status:       {s['amf_status']}")
    print(f"  SMF Status:       {s['smf_status']}")
    print(f"  UPF Status:       {s['upf_status']}")
    print()
    print(f"  Packets RX:       {s['packets_received']}")
    print(f"  Packets TX:       {s['packets_sent']}")
    print(f"  Packets Dropped:  {s['packets_dropped']}")
    print(f"  Avg Latency:      {s['avg_latency_ms']:.2f}ms")
    print(f"  Bandwidth:        {s['current_bandwidth_mbps']} Mbps")
    print("="*70 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if os.geteuid() != 0:
        print("⚠️  This script requires root privileges for IPsec setup")
        print("   Run: sudo python3 n3iwf/callbox_simulator.py")
        sys.exit(1)
    
    callbox = CallboxSimulator()
    
    # Start status printer thread
    def status_printer():
        while True:
            time.sleep(10)
            print_status()
    
    threading.Thread(target=status_printer, daemon=True).start()
    
    # Start simulator
    callbox.start()
