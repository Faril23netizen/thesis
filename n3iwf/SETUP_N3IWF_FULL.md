# 🚀 Setup N3IWF Lengkap dengan Callbox Simulator

## 📋 Overview

Setup lengkap untuk deployment N3IWF dengan simulasi Callbox 5G:

```
Pico 2W (Sensor pH & Suhu)
    ↓ WiFi (10.42.0.206 → 10.42.0.1)
RPi5 (Edge AI + N3IWF Client)
    ↓ IPsec Tunnel (192.168.100.2 → 192.168.100.1)
Callbox Simulator (5G Core: AMF, SMF, UPF)
    ↓ Virtual 5G Network
Dashboard & Monitoring
```

---

## 🔧 Prerequisites

### 1. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install strongSwan (IPsec)
sudo apt install -y strongswan strongswan-pki libcharon-extra-plugins

# Install Python dependencies
pip3 install flask requests numpy matplotlib

# Verify installation
ipsec version
```

### 2. Enable IP Forwarding

```bash
# Enable IP forwarding
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# Make permanent
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
echo "net.ipv6.conf.all.forwarding=1" | sudo tee -a /etc/sysctl.conf
```

---

## 🏗️ Setup Step-by-Step

### Step 1: Setup Callbox Simulator

```bash
# Terminal 1: Jalankan Callbox Simulator
sudo python3 n3iwf/callbox_simulator.py
```

**Output yang diharapkan:**
```
======================================================================
5G Callbox Simulator Started
======================================================================
Callbox IP: 10.42.0.1
IPsec Tunnel IP: 192.168.100.1
Base Latency: 10ms ± 5ms
Packet Loss Rate: 1.0%
Bandwidth: 100 Mbps
======================================================================
[INFO] IPsec config files created
[INFO] To activate IPsec tunnel:
  sudo cp /tmp/ipsec_callbox.conf /etc/ipsec.conf
  sudo cp /tmp/ipsec_callbox.secrets /etc/ipsec.secrets
  sudo chmod 600 /etc/ipsec.secrets
  sudo ipsec restart
[AMF] UE registered: n3iwf-client
[SMF] Session created: session-001 for UE n3iwf-client
Callbox simulator ready. Waiting for N3IWF client...
```

**Jangan close terminal ini!** Biarkan jalan.

---

### Step 2: Activate IPsec (Callbox Side)

```bash
# Terminal 2: Activate IPsec config
sudo cp /tmp/ipsec_callbox.conf /etc/ipsec.conf
sudo cp /tmp/ipsec_callbox.secrets /etc/ipsec.secrets
sudo chmod 600 /etc/ipsec.secrets
sudo ipsec restart
```

**Verify:**
```bash
sudo ipsec statusall
```

---

### Step 3: Setup N3IWF Client

```bash
# Terminal 3: Jalankan N3IWF Client
sudo python3 n3iwf/n3iwf_client.py
```

**Output yang diharapkan:**
```
======================================================================
N3IWF Client Starting...
======================================================================
Client IP: 10.42.0.1
Callbox IP: 10.42.0.1
Tunnel IP (N3IWF): 192.168.100.2
Tunnel IP (Callbox): 192.168.100.1
======================================================================
[INFO] Setting up N3IWF IPsec client...
[INFO] IPsec config installed successfully
[INFO] Starting IPsec service...
[INFO] IPsec service started
[INFO] IPsec tunnel ESTABLISHED!
[INFO] Monitoring IPsec tunnel...
✅ Tunnel ESTABLISHED
[INFO] Ping to Callbox: rtt min/avg/max/mdev = 10.2/12.5/15.3/2.1 ms
✅ Connectivity OK
```

**Jangan close terminal ini!** Biarkan jalan.

---

### Step 4: Verify Tunnel

```bash
# Terminal 4: Check tunnel status
sudo ipsec statusall | grep ESTABLISHED

# Ping through tunnel
ping -c 5 192.168.100.1

# Check routing
ip route show
```

**Expected output:**
```
n3iwf-callbox[1]: ESTABLISHED 2 seconds ago
192.168.100.0/24 dev ipsec0 proto kernel scope link src 192.168.100.2
```

---

### Step 5: Start Main Server

```bash
# Terminal 5: Jalankan server dengan N3IWF
python3 n3iwf/server.py
```

**Output:**
```
============================================================
  Aquaculture N3IWF Real Server — Progressive Learning
============================================================
  Dashboard  : http://10.42.0.1:5000
  TCP Port   : 5005 (Pico 2W)
  Mode       : REAL (data dari Pico)
  Learning   : RB(100) → FQL(200) → DQN
  RB         : ✅
  FQL        : ✅
  DQN        : ✅
  CSV Log    : results/n3iwf_real/n3iwf_real_log.csv
============================================================

[TCP] Waiting for Pico 2W on port 5005 ...
```

---

### Step 6: Access Dashboard

```bash
# Buka browser
http://10.42.0.1:5000
```

**Dashboard akan menampilkan:**
- ✅ **IPsec Status**: ESTABLISHED (hijau)
- ✅ **5G Network Stats**: Latency, jitter, PDR
- ✅ **Sensor Data**: pH & Temperature
- ✅ **Progressive AI**: RB → FQL → DQN
- ✅ **Live Charts**: Real-time monitoring

---

## 📊 Monitoring

### Check Callbox Status

```bash
# Terminal 6: Monitor Callbox
watch -n 5 'cat results/network/callbox_stats.json | python3 -m json.tool'
```

### Check N3IWF Status

```bash
# Monitor N3IWF client
watch -n 5 'cat results/network/n3iwf_status.json | python3 -m json.tool'
```

### Check IPsec Tunnel

```bash
# Real-time IPsec status
watch -n 2 'sudo ipsec statusall | grep -A 5 ESTABLISHED'
```

### Monitor Logs

```bash
# Callbox log
tail -f results/network/callbox.log

# N3IWF client log
tail -f results/network/n3iwf_client.log

# Server log
tail -f results/n3iwf_real/n3iwf_real_log.csv
```

---

## 🧪 Testing

### Test 1: Ping Through Tunnel

```bash
# From N3IWF client to Callbox
ping -c 10 192.168.100.1

# Expected: ~10-15ms latency
```

### Test 2: Measure Latency

```bash
# Run latency test
python3 latency_test.py --target 192.168.100.1 --count 100

# Results saved to: results/network/network_summary.json
```

### Test 3: Packet Loss Test

```bash
# Send 1000 packets
ping -c 1000 -i 0.01 192.168.100.1 | grep "packet loss"

# Expected: ~1% packet loss (simulated)
```

---

## 📈 Expected Results

### Network Performance

```
Metric              | Expected Value
--------------------|----------------
Avg Latency         | 10-15 ms
Min Latency         | 8-12 ms
Max Latency         | 15-20 ms
Jitter              | 3-7 ms
Packet Loss         | ~1%
Bandwidth           | 100 Mbps
```

### IPsec Tunnel

```
Status              | ESTABLISHED
Encryption          | AES-256
Authentication      | SHA-256
Key Exchange        | IKEv2
Tunnel IPs          | 192.168.100.1 ↔ 192.168.100.2
```

### 5G Core Components

```
Component           | Status
--------------------|--------
AMF                 | RUNNING
SMF                 | RUNNING
UPF                 | RUNNING
Registered UEs      | 1 (n3iwf-client)
Active Sessions     | 1 (session-001)
```

---

## 🐛 Troubleshooting

### IPsec Tunnel Not Establishing

```bash
# Check strongSwan logs
sudo journalctl -u strongswan -f

# Check IPsec status
sudo ipsec statusall

# Restart IPsec
sudo ipsec restart

# Check firewall
sudo iptables -L -n | grep 500
sudo iptables -L -n | grep 4500
```

### Ping Fails Through Tunnel

```bash
# Check routing
ip route show | grep 192.168.100

# Check tunnel interface
ip addr show | grep ipsec

# Test with tcpdump
sudo tcpdump -i any icmp
```

### Callbox Simulator Not Starting

```bash
# Check if port is in use
sudo netstat -tulpn | grep python

# Check permissions
ls -la n3iwf/callbox_simulator.py

# Run with debug
sudo python3 -u n3iwf/callbox_simulator.py
```

---

## 🔄 Restart Procedure

Kalau ada masalah, restart semua:

```bash
# 1. Stop semua
sudo pkill -f callbox_simulator
sudo pkill -f n3iwf_client
sudo pkill -f server.py
sudo ipsec stop

# 2. Clean up
sudo rm -f /var/run/charon.pid
sudo rm -f /var/run/starter.charon.pid

# 3. Start ulang (ikuti Step 1-5)
```

---

## 📚 File Structure

```
n3iwf/
├── callbox_simulator.py      # Callbox 5G simulator
├── n3iwf_client.py            # N3IWF client (RPi5)
├── server.py                  # Main server + dashboard
├── SETUP_N3IWF_FULL.md        # Dokumentasi ini
└── templates/
    └── dashboard.html         # Dashboard UI

results/
├── network/
│   ├── callbox_stats.json     # Callbox statistics
│   ├── callbox.log            # Callbox log
│   ├── n3iwf_status.json      # N3IWF status
│   ├── n3iwf_client.log       # N3IWF log
│   └── network_summary.json   # Network test results
└── n3iwf_real/
    ├── n3iwf_real_log.csv     # Main data log
    └── qtable.json            # FQL Q-table
```

---

## 🎯 For Thesis/Paper

### Claim yang Bisa Dibuat:

1. ✅ **Edge AI Deployment** di Raspberry Pi 5
2. ✅ **N3IWF Integration** dengan 5G Core
3. ✅ **IPsec Tunnel** untuk secure communication
4. ✅ **Progressive Learning** (RB → FQL → DQN)
5. ✅ **Real-time Monitoring** dengan dashboard
6. ✅ **Network Performance Analysis** (latency, jitter, PDR)
7. ✅ **5G Core Components** (AMF, SMF, UPF simulation)

### Grafik untuk Paper:

- Latency comparison: WiFi vs N3IWF/IPsec
- Progressive learning convergence
- Network performance over time
- AI inference time (RB vs FQL vs DQN)
- Water quality control effectiveness

---

## ✅ Checklist

- [ ] strongSwan installed
- [ ] IP forwarding enabled
- [ ] Callbox simulator running
- [ ] IPsec tunnel ESTABLISHED
- [ ] N3IWF client connected
- [ ] Server running
- [ ] Dashboard accessible
- [ ] Pico sending data
- [ ] Logs being written
- [ ] Network stats updating

---

**Author:** Faril  
**Date:** 2026-05-17  
**Version:** 1.0 - Full N3IWF Setup
