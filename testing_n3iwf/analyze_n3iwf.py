#!/usr/bin/env python3
"""
analyze_n3iwf.py - N3IWF Result Analysis
==========================================
Membaca results/n3iwf/n3iwf_log.csv dan generate:
  1. Grafik inference time RB vs FQL vs DQN
  2. Grafik pH & suhu over time
  3. Grafik action distribution
  4. Tabel ringkasan (CSV + print)

Usage:
  python3 testing_n3iwf/analyze_n3iwf.py
"""

import os
import sys
import csv
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N3IWF_DIR   = os.path.join(BASE_DIR, "results", "n3iwf")
N3IWF_CSV   = os.path.join(N3IWF_DIR, "n3iwf_log.csv")
OUTPUT_DIR  = N3IWF_DIR

ACTION_NAMES = ["OFF", "LOW", "MED", "HIGH"]

def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "packet":    int(row["packet_no"]),
                    "pH":        float(row["pH"]),
                    "T":         float(row["T_C"]),
                    "rb_action": row["rb_action"],
                    "fql_action":row["fql_action"],
                    "dqn_action":row["dqn_action"],
                    "rb_ms":     float(row["rb_ms"]),
                    "fql_ms":    float(row["fql_ms"]),
                    "dqn_ms":    float(row["dqn_ms"]),
                    "latency_ms":float(row["latency_ms"]),
                })
            except (ValueError, KeyError):
                continue
    return rows

def print_summary(rows):
    n = len(rows)
    rb_ms  = np.array([r["rb_ms"]  for r in rows])
    fql_ms = np.array([r["fql_ms"] for r in rows])
    dqn_ms = np.array([r["dqn_ms"] for r in rows])
    pH     = np.array([r["pH"]     for r in rows])
    T      = np.array([r["T"]      for r in rows])
    lat    = np.array([r["latency_ms"] for r in rows])

    rb_acts  = [r["rb_action"]  for r in rows]
    fql_acts = [r["fql_action"] for r in rows]
    dqn_acts = [r["dqn_action"] for r in rows]

    print("\n" + "="*60)
    print("  N3IWF EDGE INFERENCE — SUMMARY TABLE")
    print("="*60)
    print(f"  Total packets    : {n}")
    print(f"  pH  range        : {pH.min():.3f} – {pH.max():.3f}  (avg {pH.mean():.3f})")
    print(f"  Suhu range       : {T.min():.2f} – {T.max():.2f}°C  (avg {T.mean():.2f}°C)")
    if lat.max() > 0:
        print(f"  Latency avg      : {lat.mean():.1f} ms")
    print()
    print(f"  {'Algorithm':<10} {'Avg (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10} {'Std (ms)':>10}")
    print(f"  {'-'*50}")
    for label, arr in [("Rule-Based", rb_ms), ("FQL", fql_ms), ("DQN", dqn_ms)]:
        if arr.mean() > 0:
            print(f"  {label:<10} {arr.mean():>10.4f} {arr.min():>10.4f} {arr.max():>10.4f} {arr.std():>10.4f}")
    print()
    print(f"  Action Distribution:")
    print(f"  {'Action':<8} {'Rule-Based':>12} {'FQL':>12} {'DQN':>12}")
    print(f"  {'-'*46}")
    for a in ["OFF", "LOW", "MED", "HIGH"]:
        rb_pct  = rb_acts.count(a)  / n * 100
        fql_pct = fql_acts.count(a) / n * 100
        dqn_pct = dqn_acts.count(a) / n * 100
        print(f"  {a:<8} {rb_pct:>11.1f}% {fql_pct:>11.1f}% {dqn_pct:>11.1f}%")
    print("="*60 + "\n")

    # Simpan tabel ke CSV
    summary_path = os.path.join(OUTPUT_DIR, "n3iwf_summary.csv")
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "Rule-Based", "FQL", "DQN"])
        w.writerow(["avg_inference_ms", f"{rb_ms.mean():.4f}", f"{fql_ms.mean():.4f}", f"{dqn_ms.mean():.4f}"])
        w.writerow(["min_inference_ms", f"{rb_ms.min():.4f}", f"{fql_ms.min():.4f}", f"{dqn_ms.min():.4f}"])
        w.writerow(["max_inference_ms", f"{rb_ms.max():.4f}", f"{fql_ms.max():.4f}", f"{dqn_ms.max():.4f}"])
        w.writerow(["std_inference_ms", f"{rb_ms.std():.4f}", f"{fql_ms.std():.4f}", f"{dqn_ms.std():.4f}"])
        for a in ["OFF", "LOW", "MED", "HIGH"]:
            w.writerow([f"action_{a}_pct",
                        f"{rb_acts.count(a)/n*100:.1f}",
                        f"{fql_acts.count(a)/n*100:.1f}",
                        f"{dqn_acts.count(a)/n*100:.1f}"])
    print(f"  Summary CSV saved: {summary_path}")

def plot_all(rows):
    n      = len(rows)
    pkt    = np.array([r["packet"]    for r in rows])
    pH     = np.array([r["pH"]        for r in rows])
    T      = np.array([r["T"]         for r in rows])
    rb_ms  = np.array([r["rb_ms"]     for r in rows])
    fql_ms = np.array([r["fql_ms"]    for r in rows])
    dqn_ms = np.array([r["dqn_ms"]    for r in rows])

    rb_acts  = [r["rb_action"]  for r in rows]
    fql_acts = [r["fql_action"] for r in rows]
    dqn_acts = [r["dqn_action"] for r in rows]

    fig = plt.figure(figsize=(16, 18))
    fig.suptitle("N3IWF Edge AI — Inference Analysis (RB vs FQL vs DQN)",
                 fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.35)

    # 1. pH over time
    ax = fig.add_subplot(gs[0, :])
    ax.plot(pkt, pH, color="#2980b9", linewidth=0.8)
    ax.axhline(6.5, color="red", linestyle=":", linewidth=0.8, alpha=0.6, label="Safe range")
    ax.axhline(8.5, color="red", linestyle=":", linewidth=0.8, alpha=0.6)
    ax.fill_between(pkt, 6.5, 8.5, alpha=0.07, color="#2ecc71")
    ax.set_ylabel("pH"); ax.set_xlabel("Packet #")
    ax.set_title("pH Sensor — N3IWF Edge Node")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # 2. Suhu over time
    ax = fig.add_subplot(gs[1, :])
    ax.plot(pkt, T, color="#8e44ad", linewidth=0.8)
    ax.axhline(30.0, color="#f39c12", linestyle=":", linewidth=0.8, alpha=0.6, label="Warning 30°C")
    ax.set_ylabel("Suhu (°C)"); ax.set_xlabel("Packet #")
    ax.set_title("Suhu Sensor — N3IWF Edge Node")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # 3. Inference time comparison
    ax = fig.add_subplot(gs[2, :])
    ax.plot(pkt, rb_ms,  color="#e74c3c", linewidth=0.8, label="Rule-Based", alpha=0.8)
    ax.plot(pkt, fql_ms, color="#27ae60", linewidth=0.8, label="FQL",        alpha=0.8)
    ax.plot(pkt, dqn_ms, color="#f39c12", linewidth=0.8, label="DQN",        alpha=0.8)
    ax.set_ylabel("Inference Time (ms)"); ax.set_xlabel("Packet #")
    ax.set_title("Inference Time per Packet — Edge RPi5")
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # 4. Inference time bar chart (avg)
    ax = fig.add_subplot(gs[3, 0])
    labels = ["Rule-Based", "FQL", "DQN"]
    avgs   = [rb_ms.mean(), fql_ms.mean(), dqn_ms.mean()]
    stds   = [rb_ms.std(),  fql_ms.std(),  dqn_ms.std()]
    colors = ["#e74c3c", "#27ae60", "#f39c12"]
    bars = ax.bar(labels, avgs, color=colors, alpha=0.8, yerr=stds, capsize=5)
    for bar, avg in zip(bars, avgs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.0001,
                f"{avg:.4f}ms", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("Avg Inference Time (ms)")
    ax.set_title("Avg Inference Time Comparison")
    ax.grid(True, alpha=0.3, axis="y")

    # 5. Action distribution
    ax = fig.add_subplot(gs[3, 1])
    actions = ["OFF", "LOW", "MED", "HIGH"]
    x = np.arange(len(actions))
    w = 0.25
    rb_dist  = [rb_acts.count(a)/n*100  for a in actions]
    fql_dist = [fql_acts.count(a)/n*100 for a in actions]
    dqn_dist = [dqn_acts.count(a)/n*100 for a in actions]
    ax.bar(x - w, rb_dist,  w, label="Rule-Based", color="#e74c3c", alpha=0.8)
    ax.bar(x,     fql_dist, w, label="FQL",        color="#27ae60", alpha=0.8)
    ax.bar(x + w, dqn_dist, w, label="DQN",        color="#f39c12", alpha=0.8)
    ax.set_xticks(x); ax.set_xticklabels(actions)
    ax.set_ylabel("Usage (%)"); ax.set_title("Action Distribution — N3IWF")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3, axis="y")

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

    print(f"Loading: {N3IWF_CSV}")
    rows = load_csv(N3IWF_CSV)
    print(f"Loaded {len(rows)} records")

    if len(rows) == 0:
        print("[ERROR] Tidak ada data. Tunggu beberapa menit setelah server jalan.")
        sys.exit(1)

    print_summary(rows)
    plot_all(rows)
