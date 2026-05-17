#!/usr/bin/env python3
"""
analyze_n3iwf_real.py - N3IWF Real Data Analysis
==================================================
Membaca results/n3iwf_real/n3iwf_real_log.csv dan generate:
  1. Latency over time
  2. Jitter over time
  3. CDF latency
  4. Inference time RB vs FQL vs DQN
  5. Progressive learning: reward per phase
  6. Action distribution per phase
  7. FQL epsilon decay
  8. Tabel ringkasan network + learning

Usage:
  python3 n3iwf/analyze_n3iwf_real.py
"""

import os
import sys
import csv
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "n3iwf_real")
N3IWF_CSV  = os.path.join(RESULTS_DIR, "n3iwf_real_log.csv")
OUTPUT_DIR = RESULTS_DIR


def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "packet":     int(row["packet_no"]),
                    "pH":         float(row["pH"]),
                    "T":          float(row["T_C"]),
                    "phase":      row["phase"],
                    "action":     row["action"],
                    "reward":     float(row["reward"]),
                    "rb_ms":      float(row["rb_ms"]),
                    "fql_ms":     float(row["fql_ms"]),
                    "dqn_ms":     float(row["dqn_ms"]),
                    "latency_ms": float(row["latency_ms"]),
                    "buffer_size": int(row["buffer_size"]),
                    "fql_eps":    float(row["fql_eps"]),
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


def print_summary(rows):
    n      = len(rows)
    lat    = np.array([r["latency_ms"] for r in rows])
    rb_ms  = np.array([r["rb_ms"]      for r in rows])
    fql_ms = np.array([r["fql_ms"]     for r in rows])
    dqn_ms = np.array([r["dqn_ms"]     for r in rows])
    jitter = compute_jitter(lat)
    
    # Per phase analysis
    rb_rows  = [r for r in rows if r["phase"] == "RB"]
    fql_rows = [r for r in rows if r["phase"] == "FQL"]
    dqn_rows = [r for r in rows if r["phase"] == "DQN"]
    
    rb_reward  = np.mean([r["reward"] for r in rb_rows])  if rb_rows  else 0
    fql_reward = np.mean([r["reward"] for r in fql_rows]) if fql_rows else 0
    dqn_reward = np.mean([r["reward"] for r in dqn_rows]) if dqn_rows else 0

    print("\n" + "="*70)
    print("  N3IWF REAL DATA — PROGRESSIVE LEARNING ANALYSIS")
    print("="*70)
    print(f"  Total Packets        : {n}")
    print(f"  RB Steps             : {len(rb_rows)}")
    print(f"  FQL Steps            : {len(fql_rows)}")
    print(f"  DQN Steps            : {len(dqn_rows)}")
    print()
    print(f"  NETWORK PERFORMANCE:")
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
    print(f"  LEARNING PERFORMANCE:")
    print(f"  {'Phase':<15} {'Avg Reward':>15} {'Steps':>10}")
    print(f"  {'-'*42}")
    print(f"  {'Rule-Based':<15} {rb_reward:>15.4f} {len(rb_rows):>10}")
    print(f"  {'FQL':<15} {fql_reward:>15.4f} {len(fql_rows):>10}")
    print(f"  {'DQN':<15} {dqn_reward:>15.4f} {len(dqn_rows):>10}")
    print()
    print(f"  EDGE INFERENCE TIME (RPi5):")
    print(f"  {'Algorithm':<15} {'Avg (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10} {'Std':>10}")
    print(f"  {'-'*55}")
    for label, arr in [("Rule-Based", rb_ms), ("FQL", fql_ms), ("DQN", dqn_ms)]:
        print(f"  {label:<15} {arr.mean():>10.4f} {arr.min():>10.4f} {arr.max():>10.4f} {arr.std():>10.4f}")
    print("="*70 + "\n")

    # Save to CSV
    summary_path = os.path.join(OUTPUT_DIR, "n3iwf_real_summary.csv")
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["total_packets",        n])
        w.writerow(["rb_steps",             len(rb_rows)])
        w.writerow(["fql_steps",            len(fql_rows)])
        w.writerow(["dqn_steps",            len(dqn_rows)])
        w.writerow(["avg_latency_ms",       round(lat.mean(), 2)])
        w.writerow(["min_latency_ms",       round(lat.min(), 2)])
        w.writerow(["max_latency_ms",       round(lat.max(), 2)])
        w.writerow(["std_latency_ms",       round(lat.std(), 2)])
        w.writerow(["avg_jitter_ms",        round(jitter.mean(), 2)])
        w.writerow(["max_jitter_ms",        round(jitter.max(), 2)])
        w.writerow(["p95_latency_ms",       round(np.percentile(lat, 95), 2)])
        w.writerow(["p99_latency_ms",       round(np.percentile(lat, 99), 2)])
        w.writerow(["rb_avg_reward",        round(rb_reward, 4)])
        w.writerow(["fql_avg_reward",       round(fql_reward, 4)])
        w.writerow(["dqn_avg_reward",       round(dqn_reward, 4)])
        w.writerow(["rb_avg_inference_ms",  round(rb_ms.mean(),  4)])
        w.writerow(["fql_avg_inference_ms", round(fql_ms.mean(), 4)])
        w.writerow(["dqn_avg_inference_ms", round(dqn_ms.mean(), 4)])
    print(f"  Summary saved: {summary_path}")


def plot_all(rows):
    n      = len(rows)
    pkt    = np.array([r["packet"]     for r in rows])
    lat    = np.array([r["latency_ms"] for r in rows])
    reward = np.array([r["reward"]     for r in rows])
    rb_ms  = np.array([r["rb_ms"]      for r in rows])
    fql_ms = np.array([r["fql_ms"]     for r in rows])
    dqn_ms = np.array([r["dqn_ms"]     for r in rows])
    fql_eps= np.array([r["fql_eps"]    for r in rows])
    jitter = compute_jitter(lat)
    
    # Phase colors
    phase_colors = {"RB": "#e74c3c", "FQL": "#27ae60", "DQN": "#f39c12"}
    phases = [r["phase"] for r in rows]
    colors = [phase_colors.get(p, "#95a5a6") for p in phases]

    fig = plt.figure(figsize=(18, 22))
    fig.suptitle("N3IWF Real Data — Progressive Learning (RB → FQL → DQN)",
                 fontsize=14, fontweight="bold")
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.45, wspace=0.35)

    # 1. Latency over time
    ax = fig.add_subplot(gs[0, :])
    ax.plot(pkt, lat, color="#2980b9", linewidth=0.8, alpha=0.8, label="Latency")
    ax.axhline(lat.mean(), color="red", linestyle="--", linewidth=1,
               label=f"Avg {lat.mean():.2f} ms")
    ax.fill_between(pkt, lat.mean() - lat.std(), lat.mean() + lat.std(),
                    alpha=0.1, color="#2980b9")
    ax.set_ylabel("Latency (ms)"); ax.set_xlabel("Packet #")
    ax.set_title("End-to-End Latency — N3IWF Real Data")
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # 2. Jitter over time
    ax = fig.add_subplot(gs[1, :])
    ax.plot(pkt, jitter, color="#e67e22", linewidth=0.8, alpha=0.8, label="Jitter")
    ax.axhline(jitter.mean(), color="red", linestyle="--", linewidth=1,
               label=f"Avg {jitter.mean():.2f} ms")
    ax.set_ylabel("Jitter (ms)"); ax.set_xlabel("Packet #")
    ax.set_title("Jitter (|Δlatency|) — N3IWF Real Data")
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # 3. Reward over time (colored by phase)
    ax = fig.add_subplot(gs[2, :])
    for phase, color in phase_colors.items():
        phase_idx = [i for i, p in enumerate(phases) if p == phase]
        if phase_idx:
            ax.scatter([pkt[i] for i in phase_idx], [reward[i] for i in phase_idx],
                      c=color, s=10, alpha=0.6, label=phase)
    # Rolling average
    w = min(20, n)
    roll = lambda x: np.convolve(x, np.ones(w)/w, mode="same")
    ax.plot(pkt, roll(reward), color="black", linewidth=2, alpha=0.8, label="Rolling Avg")
    ax.axhline(0, color="gray", linestyle=":", linewidth=1)
    ax.set_ylabel("Reward"); ax.set_xlabel("Packet #")
    ax.set_title("Reward Over Time — Progressive Learning")
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # 4. CDF Latency
    ax = fig.add_subplot(gs[3, 0])
    sorted_lat = np.sort(lat)
    cdf = np.arange(1, n + 1) / n
    ax.plot(sorted_lat, cdf, color="#2980b9", linewidth=1.5)
    ax.axvline(np.percentile(lat, 95), color="red", linestyle="--",
               linewidth=1, label=f"P95={np.percentile(lat,95):.1f}ms")
    ax.axvline(np.percentile(lat, 99), color="darkred", linestyle=":",
               linewidth=1, label=f"P99={np.percentile(lat,99):.1f}ms")
    ax.set_xlabel("Latency (ms)"); ax.set_ylabel("CDF")
    ax.set_title("CDF Latency")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # 5. Latency histogram
    ax = fig.add_subplot(gs[3, 1])
    ax.hist(lat, bins=30, color="#2980b9", alpha=0.7, edgecolor="white")
    ax.axvline(lat.mean(), color="red", linestyle="--", linewidth=1.5,
               label=f"Mean={lat.mean():.2f}ms")
    ax.set_xlabel("Latency (ms)"); ax.set_ylabel("Frekuensi")
    ax.set_title("Distribusi Latency")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # 6. Inference time bar chart
    ax = fig.add_subplot(gs[4, 0])
    labels = ["Rule-Based", "FQL", "DQN"]
    avgs   = [rb_ms.mean(), fql_ms.mean(), dqn_ms.mean()]
    stds   = [rb_ms.std(),  fql_ms.std(),  dqn_ms.std()]
    colors_bar = ["#e74c3c", "#27ae60", "#f39c12"]
    bars = ax.bar(labels, avgs, color=colors_bar, alpha=0.8, yerr=stds, capsize=6)
    for bar, avg in zip(bars, avgs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(stds)*0.05,
                f"{avg:.4f}ms", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.set_ylabel("Avg Inference Time (ms)")
    ax.set_title("Edge Inference Time — RPi5")
    ax.grid(True, alpha=0.3, axis="y")

    # 7. FQL Epsilon Decay
    ax = fig.add_subplot(gs[4, 1])
    fql_idx = [i for i, p in enumerate(phases) if p == "FQL"]
    if fql_idx:
        ax.plot([pkt[i] for i in fql_idx], [fql_eps[i] for i in fql_idx],
                color="#27ae60", linewidth=1.5, marker="o", markersize=2)
        ax.set_ylabel("Epsilon"); ax.set_xlabel("Packet #")
        ax.set_title("FQL Epsilon Decay (Exploration → Exploitation)")
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "No FQL data", ha="center", va="center", fontsize=12)
        ax.set_title("FQL Epsilon Decay")

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    path = os.path.join(OUTPUT_DIR, "n3iwf_real_analysis.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {path}")
    plt.show()


if __name__ == "__main__":
    if not os.path.exists(N3IWF_CSV):
        print(f"[ERROR] File tidak ditemukan: {N3IWF_CSV}")
        print("  Jalankan dulu: python3 n3iwf/server.py")
        sys.exit(1)

    rows = load_csv(N3IWF_CSV)
    print(f"Loaded {len(rows)} records dari {N3IWF_CSV}")

    if len(rows) < 10:
        print("[ERROR] Data terlalu sedikit. Tunggu beberapa menit dulu.")
        sys.exit(1)

    print_summary(rows)
    plot_all(rows)
