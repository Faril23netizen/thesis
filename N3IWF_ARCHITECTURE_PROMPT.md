# 🎨 Prompt untuk Membuat Arsitektur N3IWF

Copy-paste prompt ini ke ChatGPT/Claude untuk generate diagram arsitektur N3IWF.

---

## 📋 PROMPT:

```
Buatkan diagram arsitektur sistem N3IWF (Non-3GPP Interworking Function) untuk thesis aquaculture dengan detail berikut:

## KOMPONEN SISTEM:

### 1. PICO 2W (IoT Device)
- Sensor: pH & Temperature
- Aktuator: Relay Aerator (OFF, LOW, MED, HIGH)
- Koneksi: WiFi TCP ke RPi5 (port 5005)
- IP: 10.42.0.206

### 2. RASPBERRY PI 5 (Edge AI + N3IWF Client)
- IP: 10.42.0.1 (USB tethering/hotspot mode)
- Komponen:
  a) WiFi Bridge (port 5005) - menerima data dari Pico
  b) AI Controller:
     - Phase 1: Rule-Based (100 steps)
     - Phase 2: FQL Training (200 steps)
     - Phase 3: DQN (continuous)
  c) N3IWF Client (IPsec tunnel initiator)
     - Tunnel IP: 192.168.100.2/32
     - Protocol: IKEv2/IPsec
     - Auth: PSK (Pre-Shared Key)
  d) Dashboard (port 5000)
     - Real-time monitoring
     - Network performance metrics

### 3. CALLBOX 5G SIMULATOR (5G Core Network)
- IP: 10.42.0.1 (same machine as RPi5 for simulation)
- Tunnel IP: 192.168.100.1/32
- Komponen 5G Core:
  a) AMF (Access and Mobility Management Function)
     - Register UE (User Equipment)
     - Status: RUNNING
  b) SMF (Session Management Function)
     - Create PDU sessions
     - QoS management
     - Status: RUNNING
  c) UPF (User Plane Function)
     - Forward packets
     - Simulate latency (10-15ms)
     - Simulate packet loss (~1%)
     - Status: RUNNING
  d) N3IWF (IPsec responder)
     - Accept IPsec connections
     - Tunnel to 5G Core

## ALUR DATA:

1. **Data Collection:**
   Pico 2W → WiFi TCP → RPi5 (port 5005)
   - Sensor data: pH, Temperature
   - Frequency: Real-time

2. **AI Processing:**
   WiFi Bridge → AI Controller (RB/FQL/DQN) → Action Decision
   - Input: pH, Temperature
   - Output: Aerator action (OFF/LOW/MED/HIGH)
   - Progressive learning: RB → FQL → DQN

3. **Control Command:**
   AI Controller → WiFi Bridge → Pico 2W
   - Command: Aerator control
   - Frequency: Per step

4. **Secure Communication (N3IWF):**
   RPi5 (N3IWF Client) ←→ IPsec Tunnel ←→ Callbox (N3IWF + 5G Core)
   - Protocol: IKEv2/IPsec
   - Encryption: AES-256, SHA-256
   - Tunnel IPs: 192.168.100.2 ↔ 192.168.100.1
   - Latency: 10-15ms
   - Packet loss: ~1%

5. **5G Core Processing:**
   N3IWF → AMF (registration) → SMF (session) → UPF (forwarding)
   - UE registration
   - PDU session creation
   - Packet forwarding with QoS

6. **Monitoring:**
   All components → Dashboard (port 5000)
   - Real-time water quality
   - AI phase status
   - Network performance
   - 5G Core status

## NETWORK METRICS:

- **Latency:** 10-15ms (avg)
- **Jitter:** ±5ms
- **Packet Loss:** ~1%
- **Throughput:** 100 Mbps
- **IPsec Status:** ESTABLISHED
- **Tunnel:** IKEv2/IPsec with PSK

## SECURITY:

- **IPsec Tunnel:** AES-256-SHA-256
- **IKE:** modp2048 (Diffie-Hellman Group 14)
- **ESP:** AES-256 encryption + SHA-256 authentication
- **PSK:** "aquaculture_n3iwf_2026_secret_key"
- **DPD (Dead Peer Detection):** 30s delay, 120s timeout

## DEPLOYMENT MODE:

- **Callbox & N3IWF Client:** Same machine (RPi5) for simulation
- **Tunnel:** Loopback with virtual IPs (192.168.100.1/2)
- **Purpose:** Demonstrate N3IWF integration without physical 5G Callbox

## DIAGRAM REQUIREMENTS:

1. Tampilkan semua komponen dengan jelas
2. Gunakan warna berbeda untuk setiap layer:
   - IoT Layer (Pico): Hijau
   - Edge AI Layer (RPi5): Biru
   - Network Layer (IPsec): Oranye
   - 5G Core Layer (Callbox): Merah
3. Tunjukkan alur data dengan panah
4. Label setiap koneksi dengan protocol dan port
5. Tampilkan metrics penting (latency, packet loss)
6. Gunakan icon yang sesuai untuk setiap komponen
7. Format: Professional, suitable for thesis/paper

## STYLE:

- Clean and professional
- Suitable for academic thesis
- Clear labels and legends
- Show both data flow and control flow
- Highlight IPsec tunnel security
```

---

## 🎯 TIPS PENGGUNAAN:

1. **Untuk Diagram Sederhana:**
   - Fokus pada alur utama: Pico → RPi5 → IPsec → 5G Core
   - Tampilkan 3 layer: IoT, Edge AI, 5G Core

2. **Untuk Diagram Detail:**
   - Tampilkan semua komponen 5G Core (AMF, SMF, UPF)
   - Tunjukkan progressive learning (RB → FQL → DQN)
   - Include network metrics

3. **Untuk Paper/Thesis:**
   - Gunakan format landscape
   - High resolution (300 DPI)
   - Black & white friendly (jika perlu print)

---

## 📊 ALTERNATIF TOOLS:

Jika ingin buat manual:
- **Draw.io:** https://app.diagrams.net/
- **Lucidchart:** https://www.lucidchart.com/
- **PlantUML:** Text-based diagram
- **Mermaid:** Markdown-based diagram

---

## 🔍 REFERENSI STANDAR:

- **3GPP TS 23.501:** 5G System Architecture
- **3GPP TS 24.502:** N3IWF Procedures
- **RFC 7296:** IKEv2 Protocol
- **RFC 4303:** ESP (Encapsulating Security Payload)

---

**Ready to generate!** 🚀
