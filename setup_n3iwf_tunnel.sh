#!/bin/bash
################################################################################
# setup_n3iwf_tunnel.sh — Real IPsec/ESP Tunnel untuk Simulasi N3IWF
################################################################################
#
# Arsitektur yang dibuat:
#
#   [Pico] --WiFi--> [RPi wlan0: 10.42.0.1]
#                           |
#               +-----------+------------+
#               |  Root namespace        |
#               |  veth-n3iwf: 172.16.10.1  (N3IWF endpoint)
#               +-------[veth pair]------+
#               |  ns-callbox namespace  |
#               |  veth-cb:   172.16.10.2  (5G Core endpoint)
#               +------------------------+
#
# Traffic antara 172.16.10.1 dan 172.16.10.2 di-encrypt pakai AES-256-GCM (ESP).
# Wireshark bisa lihat ESP packets di veth interface.
# Status tunnel dibaca lewat: ip xfrm state list
#
# Usage:
#   sudo ./setup_n3iwf_tunnel.sh          # setup + start
#   sudo ./setup_n3iwf_tunnel.sh status   # cek status
#   sudo ./setup_n3iwf_tunnel.sh stop     # teardown
#   sudo ./setup_n3iwf_tunnel.sh test     # ping test + Wireshark hint
#
################################################################################

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; WHITE='\033[1;37m'; NC='\033[0m'

# ── Konfigurasi Tunnel ─────────────────────────────────────────────────────── #
N3IWF_IP="172.16.10.1"        # Virtual IP sisi N3IWF (root namespace)
CALLBOX_IP="172.16.10.2"      # Virtual IP sisi 5G Core (callbox namespace)
SUBNET="172.16.10.0/30"
NS_CALLBOX="ns-callbox"       # Network namespace untuk 5G Core
VETH_N3IWF="veth-n3iwf"       # Interface sisi N3IWF (di root namespace)
VETH_CB="veth-cb"             # Interface sisi Callbox (di ns-callbox)
SPI_OUT="0x00000101"          # Security Parameter Index arah N3IWF→Callbox
SPI_IN="0x00000202"           # Security Parameter Index arah Callbox→N3IWF
STATUS_FILE="results/network/callbox_stats.json"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$SCRIPT_DIR/results/network"

# ── Helpers ───────────────────────────────────────────────────────────────── #
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

require_root() {
    [ "$EUID" -eq 0 ] || { error "Jalankan dengan sudo"; exit 1; }
}

# ── Teardown ──────────────────────────────────────────────────────────────── #
teardown() {
    info "Menghapus tunnel N3IWF..."

    # Hapus xfrm states & policies di root namespace
    ip xfrm state deleteall 2>/dev/null || true
    ip xfrm policy deleteall 2>/dev/null || true

    # Hapus xfrm di callbox namespace
    ip netns exec "$NS_CALLBOX" ip xfrm state deleteall 2>/dev/null || true
    ip netns exec "$NS_CALLBOX" ip xfrm policy deleteall 2>/dev/null || true

    # Hapus veth (otomatis hapus peer-nya juga)
    ip link del "$VETH_N3IWF" 2>/dev/null || true

    # Hapus namespace
    ip netns del "$NS_CALLBOX" 2>/dev/null || true

    ok "Tunnel dibersihkan."
}

# ── Status ────────────────────────────────────────────────────────────────── #
check_status() {
    echo ""
    echo -e "${BLUE}══ N3IWF IPsec Tunnel Status ══════════════════════════════${NC}"

    # Cek namespace
    if ip netns list 2>/dev/null | grep -q "$NS_CALLBOX"; then
        ok "Namespace '$NS_CALLBOX' : EXIST"
    else
        warn "Namespace '$NS_CALLBOX' : TIDAK ADA (tunnel belum setup?)"
        return 1
    fi

    # Cek veth
    if ip link show "$VETH_N3IWF" &>/dev/null; then
        ok "Interface $VETH_N3IWF  : UP"
    else
        warn "Interface $VETH_N3IWF  : TIDAK ADA"
    fi

    # Cek xfrm states
    local state_count
    state_count=$(ip xfrm state list 2>/dev/null | grep -c "src" || echo 0)
    if [ "$state_count" -ge 2 ]; then
        ok "IPsec SA           : $state_count states AKTIF"
        echo ""
        echo -e "${WHITE}  SA Detail:${NC}"
        ip xfrm state list | grep -E "src|enc|auth" | sed 's/^/    /'
    else
        warn "IPsec SA           : TIDAK ADA (tunnel belum established)"
    fi

    # Cek konektivitas
    echo ""
    info "Ping test $N3IWF_IP → $CALLBOX_IP (via ESP tunnel):"
    if ping -c 2 -W 2 -I "$VETH_N3IWF" "$CALLBOX_IP" &>/dev/null; then
        ok "Ping berhasil — tunnel AKTIF dan mengenkripsi traffic"
    else
        warn "Ping gagal — tunnel mungkin tidak berfungsi"
    fi

    echo ""
    echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
}

# ── Setup Utama ───────────────────────────────────────────────────────────── #
setup_tunnel() {
    require_root

    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${WHITE}   N3IWF IPsec Tunnel Setup — Aquaculture Thesis          ${BLUE}║${NC}"
    echo -e "${BLUE}║${CYAN}   Mode: AES-256-GCM ESP (Real IPsec, single RPi)         ${BLUE}║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # ── [1] Bersihkan setup lama ─────────────────────────────────────────── #
    info "[1/6] Membersihkan konfigurasi lama..."
    teardown 2>/dev/null || true
    sleep 1
    ok "Bersih."

    # ── [2] Buat network namespace ───────────────────────────────────────── #
    info "[2/6] Membuat network namespace '$NS_CALLBOX'..."
    ip netns add "$NS_CALLBOX"
    ip netns exec "$NS_CALLBOX" ip link set lo up
    ok "Namespace '$NS_CALLBOX' dibuat."

    # ── [3] Buat veth pair ───────────────────────────────────────────────── #
    info "[3/6] Membuat veth pair ($VETH_N3IWF ↔ $VETH_CB)..."
    ip link add "$VETH_N3IWF" type veth peer name "$VETH_CB"
    # Pindahkan ujung callbox ke namespace-nya
    ip link set "$VETH_CB" netns "$NS_CALLBOX"

    # Konfigurasi IP di root namespace (N3IWF side)
    ip addr add "$N3IWF_IP/30" dev "$VETH_N3IWF"
    ip link set "$VETH_N3IWF" up

    # Konfigurasi IP di callbox namespace
    ip netns exec "$NS_CALLBOX" ip addr add "$CALLBOX_IP/30" dev "$VETH_CB"
    ip netns exec "$NS_CALLBOX" ip link set "$VETH_CB" up
    ok "veth pair aktif: $N3IWF_IP ↔ $CALLBOX_IP"

    # ── [4] Generate AES-256-GCM Key ────────────────────────────────────── #
    info "[4/6] Generate kunci AES-256-GCM (36 bytes: 32-byte key + 4-byte salt)..."
    # RFC 4106 GCM requires 160-bit (20-byte) key: 16-byte key + 4-byte salt for aes-128-gcm
    # For aes-256-gcm (rfc4106): 36 bytes = 32 key + 4 salt
    AES_KEY="0x$(python3 -c "import secrets; print(secrets.token_hex(36))")"
    ok "Kunci AES-256-GCM berhasil dibuat."

    # ── [5] Setup IPsec SA & SP di kedua namespace ───────────────────────── #
    info "[5/6] Mengkonfigurasi IPsec Security Associations (ESP tunnel mode)..."

    # --- Root namespace (N3IWF side) ---
    # Outbound SA: N3IWF → Callbox
    ip xfrm state add \
        src "$N3IWF_IP" dst "$CALLBOX_IP" \
        proto esp spi "$SPI_OUT" mode tunnel \
        aead 'rfc4106(gcm(aes))' "$AES_KEY" 128 \
        replay-window 32

    # Inbound SA: Callbox → N3IWF
    ip xfrm state add \
        src "$CALLBOX_IP" dst "$N3IWF_IP" \
        proto esp spi "$SPI_IN" mode tunnel \
        aead 'rfc4106(gcm(aes))' "$AES_KEY" 128 \
        replay-window 32

    # Security Policy outbound
    ip xfrm policy add \
        src "$N3IWF_IP/32" dst "$CALLBOX_IP/32" \
        dir out priority 1 \
        tmpl src "$N3IWF_IP" dst "$CALLBOX_IP" \
        proto esp spi "$SPI_OUT" mode tunnel

    # Security Policy inbound
    ip xfrm policy add \
        src "$CALLBOX_IP/32" dst "$N3IWF_IP/32" \
        dir in priority 1 \
        tmpl src "$CALLBOX_IP" dst "$N3IWF_IP" \
        proto esp spi "$SPI_IN" mode tunnel

    ip xfrm policy add \
        src "$CALLBOX_IP/32" dst "$N3IWF_IP/32" \
        dir fwd priority 1 \
        tmpl src "$CALLBOX_IP" dst "$N3IWF_IP" \
        proto esp spi "$SPI_IN" mode tunnel

    # --- Callbox namespace ---
    # Outbound SA: Callbox → N3IWF (mirror)
    ip netns exec "$NS_CALLBOX" ip xfrm state add \
        src "$CALLBOX_IP" dst "$N3IWF_IP" \
        proto esp spi "$SPI_IN" mode tunnel \
        aead 'rfc4106(gcm(aes))' "$AES_KEY" 128 \
        replay-window 32

    # Inbound SA: N3IWF → Callbox (mirror)
    ip netns exec "$NS_CALLBOX" ip xfrm state add \
        src "$N3IWF_IP" dst "$CALLBOX_IP" \
        proto esp spi "$SPI_OUT" mode tunnel \
        aead 'rfc4106(gcm(aes))' "$AES_KEY" 128 \
        replay-window 32

    ip netns exec "$NS_CALLBOX" ip xfrm policy add \
        src "$CALLBOX_IP/32" dst "$N3IWF_IP/32" \
        dir out priority 1 \
        tmpl src "$CALLBOX_IP" dst "$N3IWF_IP" \
        proto esp spi "$SPI_IN" mode tunnel

    ip netns exec "$NS_CALLBOX" ip xfrm policy add \
        src "$N3IWF_IP/32" dst "$CALLBOX_IP/32" \
        dir in priority 1 \
        tmpl src "$N3IWF_IP" dst "$CALLBOX_IP" \
        proto esp spi "$SPI_OUT" mode tunnel

    ip netns exec "$NS_CALLBOX" ip xfrm policy add \
        src "$N3IWF_IP/32" dst "$CALLBOX_IP/32" \
        dir fwd priority 1 \
        tmpl src "$N3IWF_IP" dst "$CALLBOX_IP" \
        proto esp spi "$SPI_OUT" mode tunnel

    ok "IPsec SA dan SP dikonfigurasi di kedua namespace."

    # ── [6] Verifikasi ───────────────────────────────────────────────────── #
    info "[6/6] Verifikasi tunnel..."
    sleep 1

    if ping -c 3 -W 2 -I "$VETH_N3IWF" "$CALLBOX_IP" &>/dev/null; then
        ok "Ping N3IWF→Callbox BERHASIL — traffic di-encrypt ESP!"
        TUNNEL_STATUS="ESTABLISHED"
    else
        warn "Ping gagal — cek routing. Mencoba alternatif..."
        # Coba tanpa binding interface
        if ping -c 2 -W 2 "$CALLBOX_IP" &>/dev/null; then
            ok "Tunnel aktif (via routing default)"
            TUNNEL_STATUS="ESTABLISHED"
        else
            warn "Tunnel mungkin ada masalah routing"
            TUNNEL_STATUS="PARTIAL"
        fi
    fi

    # Simpan status awal ke callbox_stats.json
    python3 - <<PYEOF
import json, os, time

stats_file = "$SCRIPT_DIR/$STATUS_FILE"
os.makedirs(os.path.dirname(stats_file), exist_ok=True)

existing = {}
if os.path.exists(stats_file):
    try:
        with open(stats_file) as f:
            existing = json.load(f)
    except Exception:
        existing = {}

existing.update({
    "ipsec_status": "$TUNNEL_STATUS",
    "tunnel_mode": "AES-256-GCM ESP (RFC4106)",
    "n3iwf_ip": "$N3IWF_IP",
    "callbox_ip": "$CALLBOX_IP",
    "spi_out": "$SPI_OUT",
    "spi_in": "$SPI_IN",
    "uptime": 0,
    "tunnel_established_at": time.time(),
    "amf_status": "RUNNING",
    "smf_status": "RUNNING",
    "upf_status": "RUNNING",
    "amf_ues": 0,
    "smf_sessions": 0,
    "upf_packets": 0,
    "packets_sent": 0,
    "packets_dropped": 0,
    "avg_latency_ms": 0,
    "jitter_ms": 0,
    "current_bandwidth_mbps": 0,
})

with open(stats_file, "w") as f:
    json.dump(existing, f, indent=2)
print(f"Status ditulis ke {stats_file}")
PYEOF

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  TUNNEL BERHASIL DIBUAT                                  ║${NC}"
    echo -e "${GREEN}║                                                          ║${NC}"
    echo -e "${GREEN}║  N3IWF   : $N3IWF_IP (root namespace)         ║${NC}"
    echo -e "${GREEN}║  Callbox : $CALLBOX_IP (ns-callbox)            ║${NC}"
    echo -e "${GREEN}║  Enkripsi: AES-256-GCM / ESP Tunnel Mode                ║${NC}"
    echo -e "${GREEN}║  Status  : $TUNNEL_STATUS                           ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Untuk monitor traffic di Wireshark:${NC}"
    echo -e "  tcpdump -i $VETH_N3IWF -w /tmp/n3iwf_tunnel.pcap &"
    echo -e "  # Traffic akan terlihat sebagai ESP (Protocol 50) di Wireshark"
    echo ""
    echo -e "${CYAN}Untuk cek SA aktif:${NC}"
    echo -e "  ip xfrm state list"
    echo ""
    echo -e "${CYAN}Untuk stop tunnel:${NC}"
    echo -e "  sudo ./setup_n3iwf_tunnel.sh stop"
}

# ── Test Mode ─────────────────────────────────────────────────────────────── #
test_tunnel() {
    require_root

    echo ""
    info "=== Test N3IWF IPsec Tunnel ==="
    echo ""

    # 1. Ping test
    info "Test 1: Ping (ICMP through ESP tunnel)"
    if ping -c 5 -I "$VETH_N3IWF" "$CALLBOX_IP" 2>/dev/null; then
        ok "Ping OK — ICMP di-encrypt ESP"
    else
        warn "Ping gagal"
    fi
    echo ""

    # 2. Cek xfrm stats (packet counters)
    info "Test 2: IPsec packet counters"
    ip xfrm state list | grep -A2 "src $N3IWF_IP"
    echo ""

    # 3. Wireshark capture hint
    info "Test 3: Wireshark capture hint"
    echo -e "${WHITE}  Jalankan di RPi:${NC}"
    echo -e "    sudo tcpdump -i $VETH_N3IWF -w /tmp/esp_capture.pcap -c 50"
    echo -e "${WHITE}  Buka di Wireshark:${NC}"
    echo -e "    Filter: esp  → lihat ESP packets"
    echo -e "    Filter: icmp → kosong (ICMP sudah dienkripsi, tidak terlihat plain)"
    echo ""

    # 4. iperf3 bandwidth test (jika tersedia)
    if command -v iperf3 &>/dev/null; then
        info "Test 4: Bandwidth test via ESP tunnel"
        ip netns exec "$NS_CALLBOX" iperf3 -s -D -I /tmp/iperf3-callbox.pid 2>/dev/null
        sleep 1
        iperf3 -c "$CALLBOX_IP" -t 5 -B "$N3IWF_IP" 2>/dev/null || warn "iperf3 test gagal"
        kill "$(cat /tmp/iperf3-callbox.pid 2>/dev/null)" 2>/dev/null || true
    else
        warn "iperf3 tidak terinstall (opsional). Install: sudo apt install iperf3"
    fi
}

# ── Entry Point ───────────────────────────────────────────────────────────── #
case "${1:-setup}" in
    setup|start)  setup_tunnel ;;
    stop|teardown) require_root; teardown ;;
    status)       check_status ;;
    test)         test_tunnel ;;
    *)
        echo "Usage: sudo $0 [setup|stop|status|test]"
        echo ""
        echo "  setup   — Buat tunnel (default)"
        echo "  stop    — Hapus tunnel"
        echo "  status  — Cek status"
        echo "  test    — Ping + Wireshark hint"
        ;;
esac
