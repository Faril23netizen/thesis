import os
import sys
import dpkt
import socket
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PCAP_FILE = os.path.join(BASE_DIR, "results", "network", "qos_real.pcap")
OUTPUT_PLOT = os.path.join(BASE_DIR, "results", "network", "pcap_analysis.png")
OUTPUT_CSV = os.path.join(BASE_DIR, "results", "network", "pcap_stats.csv")

if not os.path.exists(PCAP_FILE):
    print(f"File {PCAP_FILE} tidak ditemukan!")
    sys.exit(1)

print(f"Menganalisis file PCAP: {PCAP_FILE}")

# Data collection
timestamps = []
packet_sizes = []
inter_arrival_times = []

last_ts = None
total_packets = 0
total_bytes = 0

with open(PCAP_FILE, 'rb') as f:
    try:
        try:
            pcap = dpkt.pcap.Reader(f)
        except ValueError:
            f.seek(0)
            pcap = dpkt.pcapng.Reader(f)
            
        for ts, buf in pcap:
            total_packets += 1
            total_bytes += len(buf)
            
            timestamps.append(ts)
            packet_sizes.append(len(buf))
            
            if last_ts is not None:
                # Calculate inter-arrival time in milliseconds
                iat = (ts - last_ts) * 1000.0
                inter_arrival_times.append(iat)
            else:
                inter_arrival_times.append(0.0)
                
            last_ts = ts
    except Exception as e:
        print(f"Peringatan: Berhenti membaca pcap di tengah karena error (mungkin capture belum selesai): {e}")

if total_packets == 0:
    print("Tidak ada paket di dalam file PCAP!")
    sys.exit(0)

# Convert timestamps to relative seconds
start_time = timestamps[0]
relative_times = [t - start_time for t in timestamps]
duration = timestamps[-1] - timestamps[0]

if duration == 0:
    print("Durasi terlalu singkat untuk dianalisis.")
    sys.exit(0)

print(f"\n--- RINGKASAN CAPTURE WIRESHARK ---")
print(f"Total Paket      : {total_packets}")
print(f"Total Data       : {total_bytes / 1024:.2f} KB")
print(f"Durasi Capture   : {duration:.2f} detik")
print(f"Average Bandwidth: {(total_bytes * 8) / duration / 1024:.2f} Kbps")
print(f"Average Jitter   : {np.mean(inter_arrival_times):.2f} ms")
print(f"Max Jitter       : {np.max(inter_arrival_times):.2f} ms")
print(f"Min Jitter       : {np.min(inter_arrival_times):.2f} ms")

# --- Time Series Aggregation (1-second windows) ---
df = pd.DataFrame({
    'timestamp': timestamps,
    'size_bytes': packet_sizes,
    'iat_ms': inter_arrival_times
})

# Convert to datetime index
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
df.set_index('datetime', inplace=True)

# Resample to 1 second intervals
throughput_kbps = (df['size_bytes'].resample('1S').sum() * 8) / 1024
avg_jitter_ms = df['iat_ms'].resample('1S').mean()
packet_count = df['size_bytes'].resample('1S').count()

# Save to CSV
stats_df = pd.DataFrame({
    'throughput_kbps': throughput_kbps,
    'avg_jitter_ms': avg_jitter_ms,
    'packet_count': packet_count
})
stats_df.to_csv(OUTPUT_CSV)
print(f"Data tersimpan di {OUTPUT_CSV}")

# --- Plotting ---
plt.style.use('dark_background')
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

# Plot 1: Bandwidth Over Time
ax1.plot(throughput_kbps.index, throughput_kbps.values, color='#00FFCC', linewidth=2)
ax1.fill_between(throughput_kbps.index, throughput_kbps.values, color='#00FFCC', alpha=0.3)
ax1.set_title("N3IWF Network Throughput (Bandwidth)", fontsize=14, color='white', pad=15)
ax1.set_ylabel("Kbps", color='white', fontsize=12)
ax1.grid(True, alpha=0.2)
ax1.tick_params(colors='white')

# Plot 2: Jitter / Inter-Arrival Time
ax2.plot(avg_jitter_ms.index, avg_jitter_ms.values, color='#FF5555', linewidth=2)
ax2.fill_between(avg_jitter_ms.index, avg_jitter_ms.values, color='#FF5555', alpha=0.3)
ax2.set_title("Network Jitter (Average Packet Inter-Arrival Time)", fontsize=14, color='white', pad=15)
ax2.set_ylabel("Jitter (ms)", color='white', fontsize=12)
ax2.set_xlabel("Time", color='white', fontsize=12)
ax2.grid(True, alpha=0.2)
ax2.tick_params(colors='white')

plt.tight_layout()
plt.savefig(OUTPUT_PLOT, dpi=150, bbox_inches='tight', facecolor='#1E1E2E')
plt.close()
print(f"Grafik tersimpan di {OUTPUT_PLOT}")
