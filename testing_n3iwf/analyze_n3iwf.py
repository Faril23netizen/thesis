#!/usr/bin/env python3
"""
analyze_n3iwf.py - N3IWF Network Performance Analysis
=======================================================
Membaca results/n3iwf/n3iwf_log.csv dan generate:
  1. Latency over time
  2. Jitter (variasi latency) over time
  3. CDF latency per algoritma
  4. Inference time RB vs FQL vs DQN
  5. PDR (Packet Delivery Rate)
  6. Tabel ringkasan network + inference

Usage:
  python3 testing_n3iwf/analyze_n3iwf.py
"""

import os
import sys
import csv
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N3IWF_DIR  = os.path.join(BASE_DIR, "results", "n3iwf")
N3IWF_CSV  = os.path.join(N3IWF_DIR, "n3iwf_log.csv")
OUTPUT_DIR = N3IWF_DIR


def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "packet":     int(row["packet_no"]),
                    "rb_action":  row["rb_action"],
                    "fql_action": row["fql_action"],
                    "dqn_action": row["dqn_action"],
                    "rb_ms":      float(row["rb_ms"]),
                    "fql_ms":     float(row["fql_ms"]),
                    "dqn_ms":     float(row["dqn_ms"]),
                    "latency_ms": float(row["latency_ms"]),
                })
            except (ValueError, KeyError):
                continue
    return rows


def compute_jitter(latency):
    """Jitter = rata-rata |latency[i] - latency[i-1]|"""
    if len(latency) < 2:
        return np.zeros(len(latency))
    diff = np.abs(np.diff(latency))
    return np.concatenate([[0], diff])


def print_summary(rows, net_avg, net_min, net_max, net_jitter, net_pdr):
    n      = len(rows)
    lat    = np.array([r["latency_ms"] for r in rows])
    rb_ms  = np.array([r["rb_ms"]      for r in rows])
    fql_ms = np.array([r["fql_ms"]     for r in rows])
    dqn_ms = np.array([r["dqn_ms"]     for r in rows])
    jitter = compute_jitter(lat)

    print("\n" + "="*65)
    print("  N3IWF NETWORK PERFORMANCE — SUMMARY TABLE")
    print("="*65)
    print(f"  Total Packets        : {n}")
    print(f"  PDR (%)              : {net_pdr}")
    print()
    print(f"  {'Metric':<25} {'Value':>15}")
    print(f"  {'-'*42}")
    print(f"  {'Avg Latency (ms)':<25} {lat.mean():>15.2f}")
    print(f"  {'Min Latency (ms)':<25} {lat.min():>15.2f}")
    print(f"  {'Max Latency (ms)':<25} {lat.max():>15.2f}")
    print(f"  {'Avg Jitter (ms)':<25} {jitter.mean():>15.2f}")
    print(f"  {'Max Jitter (ms)':<25} {jitter.max():>15.2f}")
    print(f"  {'Std Latency (ms)':<25} {lat.std():>15.2f}")
    print(f"  {'P95 Latency (ms)':<25} {np.percentile(lat, 95):>15.2f}")
    print(f"  {'P99 Latency (ms)':<25} {np.percentile(lat, 99):>15.2f}")
    print()
    print(f"  EDGE INFERENCE TIME (RPi5):")
    print(f"  {'Algorithm':<15} {'Avg (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10} {'Std':>10}")
    print(f"  {'-'*55}")
    for label, arr in [("Rule-Based", rb_ms), ("FQL", fql_ms), ("DQN", dqn_ms)]:
        print(f"  {label:<15} {arr.mean():>10.4f} {arr.min():>10.4f} {arr.max():>10.4f} {arr.std():>10.4f}")
    print("="*65 + "\n")

    # Simpan ke CSV
    summary_path = os.path.join(OUTPUT_DIR, "n3iwf_summary.csv")
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["total_packets",        n])
        w.writerow(["pdr_pct",              net_pdr])
        w.writerow(["avg_latency_ms",       round(lat.mean(), 2)])
        w.writerow(["min_latency_ms",       round(lat.min(), 2)])
        w.writerow(["max_latency_ms",       round(lat.max(), 2)])
        w.writerow(["std_latency_ms",       round(lat.std(), 2)])
        w.writerow(["avg_jitter_ms",        round(jitter.mean(), 2)])
        w.writerow(["max_jitter_ms",        round(jitter.max(), 2)])
        w.writerow(["p95_latency_ms",       round(np.percentile(lat, 95), 2)])
        w.writerow(["p99_latency_ms",       round(np.percentile(lat, 99), 2)])
        w.writerow(["rb_avg_inference_ms",  round(rb_ms.mean(),  4)])
        w.writerow(["fql_avg_inference_ms", round(fql_ms.mean(), 4)])
        w.writerow(["dqn_avg_inference_ms", round(dqn_ms.mean(), 4)])
    print(f"  Summary saved: {summary_path}")


def plot_all(rows):
    n      = len(rows)
    pkt    = np.array([r["packet"]     for r in rows])
    lat    = np.array([r["latency_ms"] for r in rows])
    rb_ms  = np.array([r["rb_ms"]      for r in rows])
    fql_ms = np.array([r["fql_ms"]     for r in rows])
    dqn_ms = np.array([r["dqn_ms"]     for r in rows])
    jitter = compute_jitter(lat)

    fig = plt.figure(figsize=(16, 20))
    fig.suptitle("N3IWF 5G Network Performance — Aquaculture Edge AI",
                 fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.35)

    # 1. Latency over time
    ax = fig.add_subplot(gs[0, :])
    ax.plot(pkt, lat, color="#2980b9", linewidth=0.8, alpha=0.8, label="Latency")
    ax.axhline(lat.mean(), color="red", linestyle="--", linewidth=1,
               label=f"Avg {lat.mean():.2f} ms")
    ax.fill_between(pkt, lat.mean() - lat.std(), lat.mean() + lat.std(),
                    alpha=0.1, color="#2980b9")
    ax.set_ylabel("Latency (ms)"); ax.set_xlabel("Packet #")
    ax.set_title("End-to-End Latency — N3IWF IPsec Tunnel")
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # 2. Jitter over time
    ax = fig.add_subplot(gs[1, :])
    ax.plot(pkt, jitter, color="#e67e22", linewidth=0.8, alpha=0.8, label="Jitter")
    ax.axhline(jitter.mean(), color="red", linestyle="--", linewidth=1,
               label=f"Avg {jitter.mean():.2f} ms")
    ax.set_ylabel("Jitter (ms)"); ax.set_xlabel("Packet #")
    ax.set_title("Jitter (|Δlatency|) — N3IWF Tunnel")
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # 3. CDF Latency
    ax = fig.add_subplot(gs[2, 0])
    sorted_lat = np.sort(lat)
    cdf = np.arange(1, n + 1) / n
    ax.plot(sorted_lat, cdf, color="#2980b9", linewidth=1.5)
    ax.axvline(np.percentile(lat, 95), color="red", linestyle="--",
               linewidth=1, label=f"P95={np.percentile(lat,95):.1f}ms")
    ax.axvline(np.percentile(lat, 99), color="darkred", linestyle=":",
               linewidth=1, label=f"P99={np.percentile(lat,99):.1f}ms")
    ax.set_xlabel("Latency (ms)"); ax.set_ylabel("CDF")
    ax.set_title("CDF Latency — N3IWF")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # 4. Latency histogram
    ax = fig.add_subplot(gs[2, 1])
    ax.hist(lat, bins=30, color="#2980b9", alpha=0.7, edgecolor="white")
    ax.axvline(lat.mean(), color="red", linestyle="--", linewidth=1.5,
               label=f"Mean={lat.mean():.2f}ms")
    ax.set_xlabel("Latency (ms)"); ax.set_ylabel("Frekuensi")
    ax.set_title("Distribusi Latency")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # 5. Inference time comparison bar chart
    ax = fig.add_subplot(gs[3, 0])
    labels = ["Rule-Based", "FQL", "DQN"]
    avgs   = [rb_ms.mean(), fql_ms.mean(), dqn_ms.mean()]
    stds   = [rb_ms.std(),  fql_ms.std(),  dqn_ms.std()]
    colors = ["#e74c3c", "#27ae60", "#f39c12"]
    bars = ax.bar(labels, avgs, color=colors, alpha=0.8, yerr=stds, capsize=6)
    for bar, avg in zip(bars, avgs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(stds)*0.05,
                f"{avg:.4f}ms", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.set_ylabel("Avg Inference Time (ms)")
    ax.set_title("Edge Inference Time — RPi5 (RB vs FQL vs DQN)")
    ax.grid(True, alpha=0.3, axis="y")

    # 6. Inference time over time (rolling avg)
    ax = fig.add_subplot(gs[3, 1])
    w = min(20, n)
    roll = lambda x: np.convolve(x, np.ones(w)/w, mode="same")
    ax.plot(pkt, roll(rb_ms),  color="#e74c3c", linewidth=1.2, label="Rule-Based", alpha=0.9)
    ax.plot(pkt, roll(fql_ms), color="#27ae60", linewidth=1.2, label="FQL",        alpha=0.9)
    ax.plot(pkt, roll(dqn_ms), color="#f39c12", linewidth=1.2, label="DQN",        alpha=0.9)
    ax.set_ylabel("Inference Time (ms)"); ax.set_xlabel("Packet #")
    ax.set_title("Inference Time Over Time (rolling avg)")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    path = os.path.join(OUTPUT_DIR, "n3iwf_analysis.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {path}")
    plt.show()


if __name__ == "__main__":
    if not os.path.exists(N3IWF_CSV):
        print(f"[ERROR] File tidak ditemukan: {N3IWF_CSV}")
        print("  Jalankan dulu: PYTHONPATH=. python3 testing_n3iwf/server.py --sim")
        sys.exit(1)

    rows = load_csv(N3IWF_CSV)
    print(f"Loaded {len(rows)} records dari {N3IWF_CSV}")

    if len(rows) < 5:
        print("[ERROR] Data terlalu sedikit. Tunggu beberapa menit dulu.")
        sys.exit(1)

    # Ambil network summary dari state jika ada
    net_avg = "--"; net_min = "--"; net_max = "--"
    net_jitter = "--"; net_pdr = "--"
    ns_path = os.path.join(BASE_DIR, "results", "network", "network_summary.json")
    if os.path.exists(ns_path):
        import json
        with open(ns_path) as f:
            ns = json.load(f)
        net_avg    = ns.get("avg_ms", "--")
        net_min    = ns.get("min_ms", "--")
        net_max    = ns.get("max_ms", "--")
        net_jitter = ns.get("jitter_ms", "--")
        net_pdr    = ns.get("pdr_pct", "--")

    print_summary(rows, net_avg, net_min, net_max, net_jitter, net_pdr)
    plot_all(rows)
