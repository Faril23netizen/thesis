"""
Plot Data Sensor — dari data.csv (PuTTY log format)
====================================================
Baca data hasil collection dari Pico, tampilkan grafik:
  1. pH vs Waktu
  2. Suhu vs Waktu
  3. NH3% vs Waktu
  4. Status distribusi (pie chart)

Jalankan:
  python plot_data.py
  python plot_data.py --file path/ke/data.csv
"""

import re
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# Regex untuk parse baris data
# Contoh: "    1 |     0.0 | 8.558 | 22.00 | 14.193% | 1537 |   100K  | WARNING"
_ROW_RE = re.compile(
    r"\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|"
    r"\s*([\d.]+)%\s*\|\s*(\d+)\s*\|\s*[\d]+K\s*\|\s*(\w+)"
)

# Warna status
STATUS_COLOR = {
    "SAFE":        "#2ecc71",
    "WARNING":     "#f39c12",
    "DANGER":      "#e74c3c",
    "DANGER_PH":   "#e74c3c",
    "DANGER_TEMP": "#c0392b",
}


def parse_data(filepath: str) -> dict:
    """Parse file log PuTTY, return dict of lists."""
    data = {
        "index":  [],
        "time_s": [],
        "ph":     [],
        "temp":   [],
        "nh3":    [],
        "adc":    [],
        "status": [],
    }

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = _ROW_RE.match(line)
            if not m:
                continue
            data["index"].append(int(m.group(1)))
            data["time_s"].append(float(m.group(2)))
            data["ph"].append(float(m.group(3)))
            data["temp"].append(float(m.group(4)))
            data["nh3"].append(float(m.group(5)))
            data["adc"].append(int(m.group(6)))
            data["status"].append(m.group(7).strip())

    return data


def status_colors(status_list: list) -> list:
    """Konversi list status ke list warna untuk scatter plot."""
    return [STATUS_COLOR.get(s, "#95a5a6") for s in status_list]


def plot(data: dict, save_path: str | None = None):
    time  = np.array(data["time_s"])
    ph    = np.array(data["ph"])
    temp  = np.array(data["temp"])
    nh3   = np.array(data["nh3"])
    stat  = data["status"]
    colors = status_colors(stat)

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(
        "Aquaculture Sensor Data — RP2040 Pico",
 
    )

    # ── Panel 1: pH ──────────────────────────────────────────────────────── #
    ax1 = axes[0]
    ax1.plot(time, ph, color="#2980b9", linewidth=0.8, alpha=0.7, label="pH")
    ax1.scatter(time, ph, c=colors, s=6, zorder=3)
    ax1.axhline(6.5, color="#e74c3c", linestyle="--", linewidth=0.8, alpha=0.6, label="Batas bawah (6.5)")
    ax1.axhline(8.5, color="#e74c3c", linestyle="--", linewidth=0.8, alpha=0.6, label="Batas atas (8.5)")
    ax1.fill_between(time, 6.5, 8.5, alpha=0.05, color="#2ecc71")
    ax1.set_ylabel("pH", fontsize=10)
    ax1.set_ylim(5.5, 10.0)
    ax1.legend(fontsize=8, loc="upper right")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f"pH (min={ph.min():.3f}  max={ph.max():.3f}  avg={ph.mean():.3f})",
                  fontsize=9, loc="left")

    # ── Panel 2: Suhu ────────────────────────────────────────────────────── #
    ax2 = axes[1]
    ax2.plot(time, temp, color="#8e44ad", linewidth=0.8, alpha=0.7, label="Suhu (°C)")
    ax2.scatter(time, temp, c=colors, s=6, zorder=3)
    ax2.axhline(30.0, color="#f39c12", linestyle="--", linewidth=0.8, alpha=0.6, label="Warning (30°C)")
    ax2.axhline(35.0, color="#e74c3c", linestyle="--", linewidth=0.8, alpha=0.6, label="Danger (35°C)")
    ax2.set_ylabel("Suhu (°C)", fontsize=10)
    ax2.legend(fontsize=8, loc="upper right")
    ax2.grid(True, alpha=0.3)
    ax2.set_title(f"Suhu (min={temp.min():.2f}°C  max={temp.max():.2f}°C  avg={temp.mean():.2f}°C)",
                  fontsize=9, loc="left")

    # ── Panel 3: NH3% ────────────────────────────────────────────────────── #
    ax3 = axes[2]
    ax3.fill_between(time, nh3, alpha=0.3, color="#e67e22")
    ax3.plot(time, nh3, color="#e67e22", linewidth=0.8, alpha=0.9, label="NH3 (%)")
    ax3.axhline(0.02, color="#e74c3c", linestyle="--", linewidth=0.8, alpha=0.6,
                label="Safe limit (0.02%)")
    ax3.set_ylabel("NH3 (%)", fontsize=10)
    ax3.set_xlabel("Waktu (detik)", fontsize=10)
    ax3.legend(fontsize=8, loc="upper right")
    ax3.grid(True, alpha=0.3)
    ax3.set_title(f"NH3 (min={nh3.min():.3f}%  max={nh3.max():.3f}%  avg={nh3.mean():.3f}%)",
                  fontsize=9, loc="left")

    # ── Legend status warna (shared) ─────────────────────────────────────── #
    legend_patches = [
        mpatches.Patch(color=STATUS_COLOR["SAFE"],        label="SAFE"),
        mpatches.Patch(color=STATUS_COLOR["WARNING"],     label="WARNING"),
        mpatches.Patch(color=STATUS_COLOR["DANGER_PH"],   label="DANGER"),
    ]
    fig.legend(handles=legend_patches, loc="lower center",
               ncol=3, fontsize=9, framealpha=0.9,
               bbox_to_anchor=(0.5, 0.01))

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Grafik disimpan ke: {save_path}")

    plt.show()


def print_summary(data: dict):
    ph   = np.array(data["ph"])
    temp = np.array(data["temp"])
    nh3  = np.array(data["nh3"])
    n    = len(ph)

    # Hitung distribusi status
    from collections import Counter
    stat_count = Counter(data["status"])

    duration_s = data["time_s"][-1] if data["time_s"] else 0

    print("\n" + "=" * 55)
    print("  RINGKASAN DATA SENSOR")
    print("=" * 55)
    print(f"  Total records  : {n}")
    print(f"  Durasi         : {duration_s:.0f} s ({duration_s/60:.1f} menit)")
    print(f"  Interval       : ~{duration_s/n:.1f} s/record")
    print()
    print(f"  pH     : min={ph.min():.3f}  max={ph.max():.3f}  avg={ph.mean():.3f}  std={ph.std():.3f}")
    print(f"  Suhu   : min={temp.min():.2f}C  max={temp.max():.2f}C  avg={temp.mean():.2f}C")
    print(f"  NH3    : min={nh3.min():.3f}%  max={nh3.max():.3f}%  avg={nh3.mean():.3f}%")
    print()
    print("  Status distribusi:")
    for s, cnt in sorted(stat_count.items()):
        print(f"    {s:<15}: {cnt:5d} records ({cnt/n*100:.1f}%)")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data.csv", help="Path ke file data.csv")
    parser.add_argument("--save", default=None, help="Simpan grafik ke file PNG")
    args = parser.parse_args()

    print(f"Membaca: {args.file}")
    data = parse_data(args.file)
    print(f"Berhasil parse {len(data['ph'])} records.")

    print_summary(data)
    plot(data, save_path=args.save)
