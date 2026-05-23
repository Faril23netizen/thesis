# 🎨 Prompt untuk Membuat Arsitektur N3IWF Local Edge Service

Copy-paste prompt ini ke ChatGPT/Claude untuk generate diagram arsitektur N3IWF sebagai local edge service.

---

## 📋 PROMPT:

```
Buatkan diagram arsitektur N3IWF (Non-3GPP Interworking Function) sebagai LOCAL EDGE SERVICE untuk aquaculture monitoring system dengan detail berikut:

## KONSEP UTAMA:

N3IWF berfungsi sebagai **local edge gateway** yang menyediakan:
1. Secure communication (IPsec tunnel)
2. 5G Core Network simulation (AMF, SMF, UPF)
3. Network performance monitoring
4. Low-latency local processing

## KOMPONEN N3IWF LOCAL EDGE SERVICE:

### 1. N3IWF CLIENT (Edge Device Side)
- **Lokasi:** Raspberry Pi 5
- **IP:** 10.42.0.1
- **Tunnel IP:** 192.168.100.2/32
- **Fungsi:**
  - Initiate IPsec tunnel
  - Encrypt data traffic
  - Monitor tunnel status
- **Protocol:** IKEv2/IPsec
- **Auth:** Pre-Shared Key (PSK)

### 2. IPSEC TUNNEL (Secure Channel)
- **Protocol:** IKEv2 (Internet Key Exchange v2)
- **Encryption:** AES-256
- **Authentication:** SHA-256
- **Key Exchange:** Diffie-Hellman Group 14 (modp2048)
- **Tunnel IPs:** 192.168.100.2 ↔ 192.168.100.1
- **Metrics:**
  - Latency: 10-15ms
  - Jitter: ±5ms
  - Packet Loss: ~1%
  - Throughput: 100 Mbps

### 3. N3IWF GATEWAY (5G Core Side)
- **Lokasi:** Raspberry Pi 5 (same machine, local simulation)
- **IP:** 10.42.0.1
- **Tunnel IP:** 192.168.100.1/32
- **Fungsi:**
  - Accept IPsec connections
  - Terminate IPsec tunnel
  - Forward to 5G Core components
- **Status:** ESTABLISHED

### 4. 5G CORE NETWORK COMPONENTS (Local Simulation)

#### a) AMF (Access and Mobility Management Function)
- **Fungsi:**
  - Register UE (User Equipment)
  - Manage mobility
  - Authentication
- **Status:** RUNNING
- **Registered UE:** n3iwf-client

#### b) SMF (Session Management Function)
- **Fungsi:**
  - Create PDU sessions
  - Manage QoS (Quality of Service)
  - Session lifecycle
- **Status:** RUNNING
- **Active Sessions:** session-001
- **QoS:** QoS-1 (default)

#### c) UPF (User Plane Function)
- **Fungsi:**
  - Forward data packets
  - Apply QoS policies
  - Monitor traffic
- **Status:** RUNNING
- **Metrics:**
  - Packets sent/received
  - Packet loss simulation
  - Latency simulation

## ALUR KERJA N3IWF:

### FASE 1: TUNNEL ESTABLISHMENT
```
1. N3IWF Client (RPi5) → IKE_SA_INIT → N3IWF Gateway
   - Negotiate encryption algorithms
   - Exchange Diffie-Hellman keys

2. N3IWF Client ← IKE_SA_INIT ← N3IWF Gateway
   - Confirm algorithms
   - Send DH response

3. N3IWF Client → IKE_AUTH → N3IWF Gateway
   - Authenticate with PSK
   - Request tunnel creation

4. N3IWF Client ← IKE_AUTH ← N3IWF Gateway
   - Confirm authentication
   - Tunnel ESTABLISHED
```

### FASE 2: UE REGISTRATION
```
1. N3IWF Gateway → Registration Request → AMF
   - UE ID: n3iwf-client
   - Tunnel IP: 192.168.100.2

2. AMF → Registration Accept → N3IWF Gateway
   - UE registered
   - Status: REGISTERED
```

### FASE 3: SESSION CREATION
```
1. N3IWF Gateway → PDU Session Request → SMF
   - UE ID: n3iwf-client
   - Session ID: session-001

2. SMF → Session Created → N3IWF Gateway
   - QoS: QoS-1
   - Bandwidth: 100 Mbps
   - Status: ACTIVE
```

### FASE 4: DATA FORWARDING
```
1. Application Data → N3IWF Client (encrypt)
2. Encrypted Data → IPsec Tunnel → N3IWF Gateway (decrypt)
3. Decrypted Data → UPF (forward with QoS)
4. UPF → Simulate latency (10-15ms)
5. UPF → Check packet loss (~1%)
6. UPF → Forward to destination
```

### FASE 5: MONITORING
```
1. N3IWF Client → Check tunnel status (every 5s)
2. N3IWF Gateway → Update statistics (every 1s)
3. Statistics → Save to JSON (every 5s)
   - callbox_stats.json
   - n3iwf_status.json
4. Dashboard → Read statistics → Display metrics
```

## KEUNTUNGAN LOCAL EDGE N3IWF:

1. **Low Latency:** 10-15ms (vs 40-100ms cloud)
2. **Secure:** IPsec encryption end-to-end
3. **Reliable:** Local processing, no internet dependency
4. **Standardized:** Follow 3GPP TS 23.501 standard
5. **Scalable:** Can connect multiple edge devices
6. **Monitored:** Real-time network metrics

## DEPLOYMENT ARCHITECTURE:

```
┌─────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 5                           │
│                  (Local Edge Server)                        │
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                │
│  │  N3IWF       │ IPsec   │  N3IWF       │                │
│  │  Client      │◄───────►│  Gateway     │                │
│  │              │ Tunnel  │              │                │
│  │ 192.168.100.2│         │192.168.100.1 │                │
│  └──────────────┘         └──────┬───────┘                │
│                                   │                         │
│                          ┌────────▼────────┐               │
│                          │   5G Core       │               │
│                          │   Components    │               │
│                          │                 │               │
│                          │  ┌───────────┐  │               │
│                          │  │    AMF    │  │               │
│                          │  │ (Register)│  │               │
│                          │  └─────┬─────┘  │               │
│                          │        │        │               │
│                          │  ┌─────▼─────┐  │               │
│                          │  │    SMF    │  │               │
│                          │  │ (Session) │  │               │
│                          │  └─────┬─────┘  │               │
│                          │        │        │               │
│                          │  ┌─────▼─────┐  │               │
│                          │  │    UPF    │  │               │
│                          │  │ (Forward) │  │               │
│                          │  └───────────┘  │               │
│                          └─────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

## DIAGRAM REQUIREMENTS:

1. **Fokus pada N3IWF workflow:**
   - Tunnel establishment
   - UE registration
   - Session creation
   - Data forwarding
   - Monitoring

2. **Tampilkan layer:**
   - Application Layer (top)
   - N3IWF Client Layer
   - IPsec Tunnel Layer (highlight security)
   - N3IWF Gateway Layer
   - 5G Core Layer (bottom)

3. **Gunakan warna:**
   - N3IWF Client: Biru
   - IPsec Tunnel: Oranye (security)
   - N3IWF Gateway: Hijau
   - 5G Core: Merah

4. **Tunjukkan:**
   - Alur data dengan panah
   - Protocol di setiap koneksi
   - Metrics (latency, packet loss)
   - Status (ESTABLISHED, RUNNING)

5. **Style:**
   - Professional untuk thesis
   - Clear labels
   - Show security aspect (encryption)
   - Highlight local edge benefit

## METRICS TO DISPLAY:

- **Tunnel Status:** ESTABLISHED
- **Latency:** 10-15ms
- **Jitter:** ±5ms
- **Packet Loss:** ~1%
- **Throughput:** 100 Mbps
- **Encryption:** AES-256-SHA-256
- **Uptime:** Real-time
```

---

## 🎯 FOKUS DIAGRAM:

Diagram harus menjelaskan:
1. **Bagaimana N3IWF bekerja sebagai local edge gateway**
2. **Alur establishment IPsec tunnel**
3. **Integrasi dengan 5G Core components**
4. **Benefit: low latency, secure, local processing**

---

## 📊 OUTPUT FORMAT:

- **Landscape orientation**
- **High resolution (300 DPI)**
- **Professional style untuk thesis**
- **Clear flow: top-to-bottom atau left-to-right**

---

**Ready to generate!** 🚀
