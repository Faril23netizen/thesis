# N3IWF Setup Guide 🌐

Panduan ini menjelaskan cara mengonfigurasi **Amarisoft 5G Callbox** dan **Raspberry Pi 5** untuk menjalankan N3IWF (*Non-3GPP Interworking Function*) sebagai bagian dari Integrated System Architecture thesis ini.

## 🔄 Perbedaan: `testing_n3iwf` vs `n3iwf`

| Aspek | `testing_n3iwf/` | `n3iwf/` |
|---|---|---|
| **Mode** | Simulasi (`--sim`) | Real (data dari Pico) |
| **Data Source** | Sintetis (generated) | Pico 2W via TCP |
| **Callbox** | Tidak perlu | Opsional (bisa tanpa) |
| **Learning** | Tidak ada (hanya inference) | Progressive: RB→FQL→DQN |
| **Tujuan** | Testing network metrics | Real deployment + learning |
| **File Log** | `results/n3iwf/n3iwf_log.csv` | `results/n3iwf_real/n3iwf_real_log.csv` |
| **Analisis** | `testing_n3iwf/analyze_n3iwf.py` | `n3iwf/analyze_n3iwf_real.py` |

**Cara Jalankan:**
```bash
# Testing (simulasi tanpa hardware)
python3 testing_n3iwf/server.py --sim
python3 testing_n3iwf/analyze_n3iwf.py

# Real (dengan Pico, progressive learning)
python3 n3iwf/server.py
python3 n3iwf/analyze_n3iwf_real.py
```

## 📐 Arsitektur Jaringan

```
[Pico WH]                [Raspberry Pi 5]              [Amarisoft Callbox]
 Sensor pH+Suhu   TCP    N3IWUE (Non-3GPP UE)   IPsec  N3IWF + 5GC (AMF)
 Relay Aerator ──────►  wifi_bridge (port 5005) ──────► lten3iwf + ltemme
                          AI Controller (FQL/DQN)        5G Core Network
                          N3IWF Dashboard (port 5000)
```

**Keterangan alur:**
1. Pico WH membaca sensor dan mengirim data via Wi-Fi TCP ke RPi5 (port 5005)
2. RPi5 memproses data dengan AI (FQL→DQN) dan membuat tunnel IPsec ke Amarisoft N3IWF
3. Seluruh traffic dari RPi5 ke 5G Core Network melewati tunnel IPsec yang terstandarisasi (3GPP Release 16)

---

## 📋 Prasyarat

| Komponen | Keterangan |
|---|---|
| Amarisoft 5G Callbox | Dengan lisensi `lten3iwf` (cek: `ls /path/amarisoft/lten3iwf`) |
| Raspberry Pi 5 | OS: Ubuntu 22.04 / Raspberry Pi OS (64-bit) |
| Router Wi-Fi Lokal | Untuk menghubungkan Pico WH & RPi5 ke jaringan yang sama |
| IP Callbox N3IWF | Contoh: `192.168.1.10` (sesuaikan) |
| IP RPi5 | Contoh: `192.168.1.200` (sesuaikan) |

---

## 🔧 Bagian 1 — Konfigurasi Amarisoft Callbox

### Step 1.1 — Cek ketersediaan N3IWF
SSH ke Amarisoft Callbox lalu jalankan:
```bash
# Cek binary N3IWF tersedia
ls -la ./lten3iwf

# Cek lisensi aktif
./lten3iwf config/n3iwf.cfg
# Jika muncul "16-digit hex code", lisensi perlu diaktivasi ke Amarisoft
```

### Step 1.2 — Copy file konfigurasi ke Callbox
Dari laptop/RPi5 Anda, salin file konfigurasi:
```bash
scp n3iwf/n3iwf_amarisoft.cfg user@<IP_CALLBOX>:~/amarisoft/config/n3iwf.cfg
```

### Step 1.3 — Edit konfigurasi (sesuaikan IP)
Di Callbox, buka file `config/n3iwf.cfg` dan ganti:

```javascript
{
    local_addr: "192.168.1.10",   // ← Ganti dengan IP interface Callbox
    amf_list: [
        { addr: "127.0.0.1" }    // ← Biasanya localhost jika 5GC di Callbox yang sama
    ],
    ike: {
        psk: "AquacultureThesis2025",   // ← Bebas, tapi HARUS sama dengan RPi5
        ue_list: [
            {
                id: "aquaculture-rpi5@thesis.local",
                addr: "192.168.1.200"  // ← Ganti dengan IP RPi5
            }
        ]
    }
}
```

### Step 1.4 — Jalankan N3IWF di Callbox
```bash
# Terminal 1: Start 5G Core (AMF/MME)
sudo ./ltemme config/mme.cfg

# Terminal 2: Start N3IWF
sudo ./lten3iwf config/n3iwf.cfg

# Verifikasi koneksi N3IWF ke AMF:
# (Dalam command line monitor lten3iwf, ketik:)
ng
# Harus muncul: "NG connection: CONNECTED"
```

---

## 🍓 Bagian 2 — Konfigurasi Raspberry Pi 5 sebagai N3IWUE

> [!IMPORTANT]
> Jalankan **sekali saja** saat pertama kali setup. Setelah itu RPi5 akan otomatis terhubung ke N3IWF saat `start_edge.sh` dijalankan.

### Step 2.1 — Transfer kode ke RPi5
```bash
# Dari laptop, push ke Git dulu
git add .
git commit -m "N3IWF integration"
git push

# Di RPi5, pull kode terbaru
ssh faril@192.168.99.103
cd thesis
git pull origin main
```

### Step 2.2 — Edit IP di file konfigurasi IPsec
```bash
nano n3iwf/ipsec.conf
```

Ganti baris berikut:
```
left=192.168.1.200     # ← IP RPi5 Anda (cek: hostname -I)
right=192.168.1.10     # ← IP Amarisoft Callbox N3IWF
```

### Step 2.3 — (Opsional) Ganti PSK jika diubah di Callbox
```bash
nano n3iwf/ipsec.secrets
# Ganti "AquacultureThesis2025" dengan PSK yang sama dengan Callbox
```

### Step 2.4 — Jalankan Setup Script
```bash
sudo bash n3iwf/setup_n3iwf.sh
```

Script ini akan otomatis:
- Install `strongSwan` (IPsec client)
- Copy konfigurasi ke `/etc/ipsec.conf` dan `/etc/ipsec.secrets`
- Restart dan enable strongSwan service

### Step 2.5 — Verifikasi Tunnel IPsec
```bash
sudo ipsec statusall
```

Output yang diharapkan:
```
aquaculture-n3iwf[1]: ESTABLISHED XX seconds ago, ...
aquaculture-n3iwf{1}: INSTALLED, TUNNEL, ...
```

---

## 🚀 Bagian 3 — Menjalankan Sistem Lengkap

Setelah Callbox dan RPi5 dikonfigurasi, jalankan sistem dengan:

```bash
# Di RPi5, dari folder root thesis
./start_edge.sh
```

Script ini akan:
1. `[0]` Cek status IPsec tunnel ke Amarisoft N3IWF
2. `[1]` Start N3IWF Web Dashboard di port 5000
3. `[2]` Start AI Controller (RB → FQL → DQN)

**Monitoring:**
```bash
# Cek tunnel IPsec
sudo ipsec statusall

# Lihat log AI Controller
tail -f results/hasil_real/service.log

# Lihat log N3IWF
tail -f results/hasil_real/dashboard.log

# Log Amarisoft N3IWF (di Callbox)
tail -f /tmp/n3iwf.log
```

**Akses Dashboard:**
- Buka browser: `http://<IP_RPI5>:5000`

---

## 🛠️ Troubleshooting

| Problem | Solusi |
|---|---|
| `lten3iwf: No such file` | N3IWF license belum diaktivasi — hubungi Amarisoft/dosen |
| `IPsec tunnel: CONNECTING (not ESTABLISHED)` | Pastikan Callbox sudah menjalankan `lten3iwf` dulu sebelum `start_edge.sh` |
| `TCP connect failed` di Pico | Pastikan `N3IWF_SERVER_IP` di `main.c` adalah IP RPi5 yang benar |
| `NG connection: DISCONNECTED` | Pastikan `ltemme` (5GC/AMF) sudah berjalan sebelum `lten3iwf` |

---

## 📌 Catatan untuk Tesis

Implementasi ini mengikuti standar **3GPP Release 16 TS 23.501** untuk Non-3GPP Access via N3IWF.

- **Protokol:** IKEv2/IPsec (RFC 7296)
- **Interface:** N2 (NGAP) antara N3IWF dan AMF
- **Latency target:** ≤ 3.5 ms lokal (vs 40 ms cloud)
- **Referensi:** Amarisoft LTEN3IWF Documentation
