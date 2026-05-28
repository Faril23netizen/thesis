import os
import sys
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    import dpkt
except ImportError:
    print("Error: dpkt tidak terinstall. Jalankan: pip install dpkt")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PCAP_FILE = os.path.join(BASE_DIR, "results", "network", "qos_real.pcap")
OUTPUT_PLOT = os.path.join(BASE_DIR, "results", "network", "pcap_analysis.png")
OUTPUT_CSV = os.path.join(BASE_DIR, "results", "network", "pcap_stats.csv")

if not os.path.exists(PCAP_FILE):
    print(f"File {PCAP_FILE} tidak ditemukan!")
    sys.exit(1)

print(f"Menganalisis file PCAP: {PCAP_FILE}")

# Data arrays
timestamps = []
packet_sizes = []
inter_arrival_times = []
rtts = [] # Latencies
timestamps_rtt = []

# Tracking structures
last_ts = None
total_packets = 0
total_bytes = 0
retransmissions = 0

unacked_seqs = {} # key: expected_ack, value: (ts, seq)
seen_seqs = set() # To detect retransmissions

with open(PCAP_FILE, 'rb') as f:
    # Handle PCAP or PCAPNG
    try:
        pcap = dpkt.pcap.Reader(f)
    except ValueError:
        f.seek(0)
        pcap = dpkt.pcapng.Reader(f)
        
    try:
        for ts, buf in pcap:
            try:
                # Interface 'any' usually produces Linux SLL (Cooked Capture)
                try:
                    link_layer = dpkt.sll.SLL(buf)
                except Exception:
                    link_layer = dpkt.ethernet.Ethernet(buf)
                    
                ip = link_layer.data
                if not isinstance(ip, dpkt.ip.IP):
                    continue
                
                tcp = ip.data
                if not isinstance(tcp, dpkt.tcp.TCP):
                    continue
                    
                payload_len = len(tcp.data)
                
                # --- Packet Loss (Retransmission) Calculation ---
                if payload_len > 0:
                    seq_id = f"{ip.src}_{ip.dst}_{tcp.sport}_{tcp.dport}_{tcp.seq}"
                    if seq_id in seen_seqs:
                        retransmissions += 1
                    else:
                        seen_seqs.add(seq_id)
                
                # --- Latency (TCP RTT) Calculation ---
                if payload_len > 0:
                    # We sent data, expect ACK
                    expected_ack = tcp.seq + payload_len
                    flow_id = f"{ip.dst}_{ip.src}_{tcp.dport}_{tcp.sport}" # Reverse direction
                    unacked_seqs[f"{flow_id}_{expected_ack}"] = ts
                    
                if tcp.flags & dpkt.tcp.TH_ACK:
                    flow_id = f"{ip.src}_{ip.dst}_{tcp.sport}_{tcp.dport}"
                    ack_key = f"{flow_id}_{tcp.ack}"
                    if ack_key in unacked_seqs:
                        rtt_ms = (ts - unacked_seqs[ack_key]) * 1000.0
                        rtts.append(rtt_ms)
                        timestamps_rtt.append(ts)
                        del unacked_seqs[ack_key]

                # --- Bandwidth & Jitter Calculation ---
                total_packets += 1
                total_bytes += len(buf)
                timestamps.append(ts)
                packet_sizes.append(len(buf))
                
                if last_ts is not None:
                    # Difference between consecutive packets
                    iat = (ts - last_ts) * 1000.0
                    inter_arrival_times.append(iat)
                else:
                    inter_arrival_times.append(0.0)
                    
                last_ts = ts
                
            except Exception as e:
                continue
    except Exception as e:
        print(f"Peringatan: Berhenti membaca pcap di tengah karena error paket terpotong: {e}")

if total_packets == 0:
    print("Tidak ada paket TCP yang valid di dalam file PCAP!")
    sys.exit(0)

duration = timestamps[-1] - timestamps[0]

# Standard Jitter Calculation (Variance of Inter-Arrival Times as per RFC 3550 proxy)
jitter_variations = [abs(inter_arrival_times[i] - inter_arrival_times[i-1]) for i in range(1, len(inter_arrival_times))]
avg_jitter = np.mean(jitter_variations) if jitter_variations else 0

# Calculate Packet Loss Rate
packet_loss_rate = (retransmissions / total_packets) * 100.0 if total_packets > 0 else 0

avg_latency = np.mean(rtts) if rtts else 0
max_latency = np.max(rtts) if rtts else 0

print(f"\n--- RINGKASAN QoS (Quality of Service) WIRESHARK ---")
print(f"Total Paket TCP  : {total_packets}")
print(f"Total Data       : {total_bytes / 1024:.2f} KB")
print(f"Durasi Capture   : {duration:.2f} detik")
print(f"Average Bandwidth: {(total_bytes * 8) / duration / 1024:.2f} Kbps")
print(f"Average Latency  : {avg_latency:.2f} ms")
print(f"Max Latency      : {max_latency:.2f} ms")
print(f"Average Jitter   : {avg_jitter:.2f} ms")
print(f"Packet Loss Rate : {packet_loss_rate:.4f}% ({retransmissions} Retransmissions)")

# --- Time Series Aggregation (1-second windows) ---
df = pd.DataFrame({
    'timestamp': timestamps,
    'size_bytes': packet_sizes,
    'iat_ms': inter_arrival_times
})
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
df.set_index('datetime', inplace=True)

# Throughput (Kbps) and Jitter (ms)
throughput_kbps = (df['size_bytes'].resample('1s').sum() * 8) / 1024
# We use standard deviation of inter-arrival time in each second as Jitter
jitter_ts = df['iat_ms'].resample('1s').std().fillna(0)

# Latency (ms)
if rtts:
    df_lat = pd.DataFrame({'timestamp': timestamps_rtt, 'latency_ms': rtts})
    df_lat['datetime'] = pd.to_datetime(df_lat['timestamp'], unit='s')
    df_lat.set_index('datetime', inplace=True)
    latency_ts = df_lat['latency_ms'].resample('1s').mean().fillna(method='ffill').fillna(0)
else:
    # Fallback if no RTT matched
    latency_ts = pd.Series(0, index=throughput_kbps.index)

# Realign index to match throughput
latency_ts = latency_ts.reindex(throughput_kbps.index, method='nearest').fillna(0)

stats_df = pd.DataFrame({
    'Throughput_Kbps': throughput_kbps,
    'Latency_ms': latency_ts,
    'Jitter_ms': jitter_ts,
})
stats_df.to_csv(OUTPUT_CSV)

# --- Plotting ---
plt.style.use('dark_background')
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

# Plot 1: Bandwidth
ax1.plot(throughput_kbps.index, throughput_kbps.values, color='#00FFCC', linewidth=2)
ax1.fill_between(throughput_kbps.index, throughput_kbps.values, color='#00FFCC', alpha=0.3)
ax1.set_title("N3IWF Network Throughput (Bandwidth)", fontsize=13, color='white', pad=10)
ax1.set_ylabel("Kbps", color='white')
ax1.grid(True, alpha=0.2)

# Plot 2: Latency
ax2.plot(latency_ts.index, latency_ts.values, color='#FFD700', linewidth=2)
ax2.fill_between(latency_ts.index, latency_ts.values, color='#FFD700', alpha=0.3)
ax2.set_title("TCP Round-Trip Time (Latency)", fontsize=13, color='white', pad=10)
ax2.set_ylabel("Latency (ms)", color='white')
ax2.grid(True, alpha=0.2)

# Plot 3: Jitter
ax3.plot(jitter_ts.index, jitter_ts.values, color='#FF5555', linewidth=2)
ax3.fill_between(jitter_ts.index, jitter_ts.values, color='#FF5555', alpha=0.3)
ax3.set_title("Network Jitter (Inter-Arrival Time Variation)", fontsize=13, color='white', pad=10)
ax3.set_ylabel("Jitter (ms)", color='white')
ax3.set_xlabel("Time", color='white')
ax3.grid(True, alpha=0.2)

plt.tight_layout()
plt.savefig(OUTPUT_PLOT, dpi=150, bbox_inches='tight', facecolor='#1E1E2E')
plt.close()
print(f"Grafik tersimpan di {OUTPUT_PLOT}")
