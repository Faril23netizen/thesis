#!/usr/bin/env python3
"""
latency_test.py - 5G N3IWF Network Performance Measurement
============================================================
Jalankan di RPi5 sebelum eksperimen utama.
Output: results/network/network_summary.json + latency_plot.png

Usage:
    python3 latency_test.py
"""

import os, csv, time, subprocess, statistics, json
from datetime import datetime

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_PLT = True
except ImportError:
    HAS_PLT = False
    print("[WARN] Install matplotlib: pip3 install matplotlib --break-system-packages")

TARGET_IP    = "192.168.100.101"
N_PINGS      = 100
PING_INTERVAL = 0.5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR  = os.path.join(BASE_DIR, "results", "network")
os.makedirs(OUT_DIR, exist_ok=True)

def ping_once(ip):
    try:
        r = subprocess.run(["ping","-c","1","-W","2",ip], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "time=" in line:
                    return float(line.split("time=")[1].split(" ")[0])
    except: pass
    return None

def check_ipsec():
    try:
        r = subprocess.run(["sudo","ipsec","statusall"], capture_output=True, text=True, timeout=5)
        return "ESTABLISHED" in r.stdout
    except: return False

def run():
    print(f"\n{'='*55}\n  5G N3IWF Latency Measurement\n{'='*55}")
    print(f"  Target: {TARGET_IP} | Pings: {N_PINGS}")
    ipsec = check_ipsec()
    print(f"  IPsec : {'ESTABLISHED ✅' if ipsec else 'DOWN ⚠️'}\n")

    latencies, lost = [], 0
    csv_path = os.path.join(OUT_DIR, "latency_results.csv")

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq","timestamp","rtt_ms","status"])
        for i in range(1, N_PINGS+1):
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            rtt = ping_once(TARGET_IP)
            if rtt:
                latencies.append(rtt)
                w.writerow([i, ts, rtt, "OK"])
                print(f"  [{i:3d}/{N_PINGS}] {rtt:6.2f} ms  {'█'*int(rtt/2)}")
            else:
                lost += 1
                w.writerow([i, ts, "", "LOST"])
                print(f"  [{i:3d}/{N_PINGS}]  LOST ✗")
            if i < N_PINGS: time.sleep(PING_INTERVAL)

    if not latencies:
        print("\n[ERROR] All pings failed!"); return

    avg    = statistics.mean(latencies)
    mn     = min(latencies)
    mx     = max(latencies)
    jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
    pdr    = len(latencies) / N_PINGS * 100
    p95    = sorted(latencies)[int(len(latencies)*0.95)-1]

    print(f"\n{'='*55}  RESULTS\n{'='*55}")
    print(f"  Min     : {mn:.2f} ms")
    print(f"  Avg     : {avg:.2f} ms")
    print(f"  Max     : {mx:.2f} ms")
    print(f"  Jitter  : {jitter:.2f} ms")
    print(f"  P95     : {p95:.2f} ms")
    print(f"  PDR     : {pdr:.1f}% ({len(latencies)}/{N_PINGS})")
    print(f"  Lost    : {lost}")
    print(f"  Encrypt : AES-128-CBC IKEv2")
    print("="*55)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "target": TARGET_IP, "n_pings": N_PINGS, "ipsec_active": ipsec,
        "min_ms": round(mn,3), "avg_ms": round(avg,3), "max_ms": round(mx,3),
        "jitter_ms": round(jitter,3), "p95_ms": round(p95,3),
        "pdr_pct": round(pdr,1), "packets_lost": lost,
        "encryption": "AES-128-CBC IKEv2"
    }
    spath = os.path.join(OUT_DIR, "network_summary.json")
    with open(spath, "w") as f: json.dump(summary, f, indent=2)
    print(f"\n  Saved: {spath}")

    if HAS_PLT:
        _plot(latencies, avg, mn, mx, jitter, pdr, lost)

def _plot(latencies, avg, mn, mx, jitter, pdr, lost):
    fig = plt.figure(figsize=(14, 8))
    fig.patch.set_facecolor('#0d1117')
    gs  = gridspec.GridSpec(2, 2, hspace=0.45, wspace=0.35)
    rc  = {'axes.facecolor':'#161b22','axes.edgecolor':'#30363d',
           'axes.labelcolor':'#e6edf3','text.color':'#e6edf3',
           'xtick.color':'#7d8590','ytick.color':'#7d8590',
           'grid.color':'#21262d','grid.alpha':0.7}
    plt.rcParams.update(rc)

    # Latency over time
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(latencies, color='#58a6ff', lw=0.9, alpha=0.8)
    ax1.fill_between(range(len(latencies)), latencies, alpha=0.12, color='#58a6ff')
    ax1.axhline(avg, color='#3fb950', lw=1.5, ls='--', label=f'Avg {avg:.2f}ms')
    ax1.axhline(mn,  color='#bc8cff', lw=1, ls=':', label=f'Min {mn:.2f}ms')
    ax1.axhline(mx,  color='#f85149', lw=1, ls=':', label=f'Max {mx:.2f}ms')
    ax1.set_title('RPi5 → Callbox RTT via IPsec N3IWF Tunnel', fontweight='bold')
    ax1.set_xlabel('Ping #'); ax1.set_ylabel('RTT (ms)')
    ax1.legend(fontsize=9); ax1.grid(True)

    # Histogram
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.hist(latencies, bins=20, color='#58a6ff', alpha=0.8, edgecolor='#30363d')
    ax2.axvline(avg, color='#3fb950', lw=2, ls='--', label=f'Mean {avg:.2f}ms')
    ax2.set_title('Latency Distribution', fontweight='bold')
    ax2.set_xlabel('RTT (ms)'); ax2.set_ylabel('Count')
    ax2.legend(fontsize=9); ax2.grid(True)

    # Summary table
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis('off')
    rows = [['Min Latency', f'{mn:.2f} ms'],
            ['Avg Latency', f'{avg:.2f} ms'],
            ['Max Latency', f'{mx:.2f} ms'],
            ['Jitter (σ)',  f'{jitter:.2f} ms'],
            ['PDR',         f'{pdr:.1f}%'],
            ['Pkt Lost',    str(lost)],
            ['Encryption',  'AES-128 IKEv2'],
            ['Tunnel',      'IPsec N3IWF']]
    t = ax3.table(cellText=rows, colLabels=['Metric','Value'],
                  cellLoc='center', loc='center', bbox=[0.05,0.05,0.9,0.9])
    t.auto_set_font_size(False); t.set_fontsize(10)
    for (r,c), cell in t.get_celld().items():
        cell.set_facecolor('#161b22' if r>0 else '#21262d')
        cell.set_edgecolor('#30363d'); cell.set_text_props(color='#e6edf3')
    ax3.set_title('Network Summary', fontweight='bold')

    fig.suptitle('5G N3IWF Network Performance — Aquaculture Edge System',
                 fontsize=13, fontweight='bold')
    path = os.path.join(OUT_DIR, "latency_plot.png")
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    print(f"  Plot : {path}")
    plt.close()

if __name__ == "__main__":
    run()
