# Troubleshooting Guide - Pico WH to RPi5 Connection

## Quick Diagnostic

Jika Pico WH tidak bisa connect ke RPi5, jalankan diagnostic tool:

```bash
cd ~/thesis
python3 diagnostic_network.py
```

Tool ini akan check:
1. ✅ Network interface (wlan0)
2. ✅ WiFi hotspot (N3IWF_AQUA)
3. ✅ IP address (10.42.0.1)
4. ✅ Firewall (port 5000)
5. ✅ Port listening
6. ✅ Connected devices
7. ✅ Ping test
8. ✅ TCP server test

## Setup WiFi Hotspot (First Time)

Jika belum setup hotspot, jalankan:

```bash
cd ~/thesis
sudo bash setup_hotspot.sh
```

Script ini akan:
- Install hostapd dan dnsmasq
- Configure wlan0 dengan IP 10.42.0.1
- Setup WiFi AP: N3IWF_AQUA / skripsi2026
- Enable DHCP server (10.42.0.2 - 10.42.0.20)
- Configure firewall

## Common Issues

### 1. WiFi Hotspot Tidak Aktif

**Symptom:** Pico tidak bisa scan SSID N3IWF_AQUA

**Fix:**
```bash
sudo systemctl start hostapd
sudo systemctl start dnsmasq
sudo systemctl status hostapd
sudo systemctl status dnsmasq
```

### 2. IP Address Salah

**Symptom:** RPi5 tidak punya IP 10.42.0.1

**Fix:**
```bash
sudo ip addr add 10.42.0.1/24 dev wlan0
ip addr show wlan0
```

### 3. Port 5000 Tidak Listening

**Symptom:** Pico connect tapi langsung disconnect

**Fix:**
```bash
# Check apa yang pakai port 5000
sudo ss -tlnp | grep 5000

# Kill process yang pakai port 5000
sudo kill <PID>

# Start server
cd ~/thesis
PYTHONPATH=~/thesis python3 main/real/run_real.py
```

### 4. Firewall Blocking

**Symptom:** Connection timeout

**Fix:**
```bash
sudo ufw allow 5000/tcp
sudo ufw status
```

### 5. Pico WiFi Error

**Symptom:** Pico serial output: "WiFi connection failed"

**Check:**
- SSID benar: N3IWF_AQUA
- Password benar: skripsi2026
- Hotspot aktif di RPi5
- Jarak Pico ke RPi5 tidak terlalu jauh

**Fix di Pico firmware:**
```c
#define WIFI_SSID "N3IWF_AQUA"
#define WIFI_PASSWORD "skripsi2026"
```

### 6. Pico TCP Connect Error

**Symptom:** Pico serial: "TCP connect failed"

**Check:**
- Server IP benar: 10.42.0.1
- Server port benar: 5000
- Server running di RPi5

**Fix di Pico firmware:**
```c
#define N3IWF_SERVER_IP "10.42.0.1"
#define N3IWF_PORT 5000
```

## Manual Testing

### Test 1: Check Hotspot

```bash
# Check if hostapd running
sudo systemctl status hostapd

# Check if dnsmasq running
sudo systemctl status dnsmasq

# Check wlan0 IP
ip addr show wlan0 | grep "inet "
```

Expected: `inet 10.42.0.1/24`

### Test 2: Check Connected Devices

```bash
# Check ARP table
arp -n | grep "10.42.0"

# Check DHCP leases
cat /var/lib/misc/dnsmasq.leases
```

Expected: Pico WH MAC address muncul

### Test 3: Test TCP Server

```bash
# Start simple TCP server
nc -l 10.42.0.1 5000
```

Kalau Pico connect, akan muncul data: `DATA:7000,2500,0`

### Test 4: Monitor Pico Serial Output

Connect Pico ke PC via USB, buka serial monitor (115200 baud):

```
# Connecting to Wi-Fi: N3IWF_AQUA ...
# Wi-Fi connected! IP: 10.42.0.2
# Connecting to 10.42.0.1:5000 ...
# TCP connected!
Sent: DATA:7015,2501,0
```

## Network Architecture

```
┌─────────────────┐
│   Pico WH       │
│  10.42.0.2      │  WiFi Client
│  (DHCP)         │
└────────┬────────┘
         │
         │ WiFi: N3IWF_AQUA
         │ Password: skripsi2026
         │
┌────────▼────────┐
│   RPi5          │
│  10.42.0.1      │  WiFi AP (hostapd)
│  wlan0          │  DHCP Server (dnsmasq)
│                 │  TCP Server (port 5000)
└─────────────────┘
```

## Protocol

**Pico → RPi5:**
```
DATA:ph_x1000,temp_x100,risk\n
```

Example:
```
DATA:7015,2501,0\n    # pH=7.015, T=25.01°C, Risk=SAFE
DATA:6850,2800,1\n    # pH=6.850, T=28.00°C, Risk=CAUTION
DATA:6500,3000,2\n    # pH=6.500, T=30.00°C, Risk=WARNING
DATA:6200,3200,3\n    # pH=6.200, T=32.00°C, Risk=CRITICAL
```

## Logs

**RPi5 Server Log:**
```bash
tail -f results/hasil_real/pico_monitor.log
```

**Pico Serial Log:**
- Connect via USB
- Open serial monitor (115200 baud)
- Watch for WiFi and TCP connection messages

## Contact

Jika masih error setelah troubleshooting:
1. Run `python3 diagnostic_network.py` dan screenshot hasilnya
2. Check Pico serial output dan screenshot
3. Check RPi5 server log: `tail -f results/hasil_real/pico_monitor.log`
