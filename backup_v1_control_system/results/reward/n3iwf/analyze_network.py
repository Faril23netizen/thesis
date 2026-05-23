#!/usr/bin/env python3
import os
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# PENGATURAN TEMA AKADEMIS (THESIS / PAPER READY)
# ---------------------------------------------------------
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif', 'serif'],
    'font.size': 12,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'axes.labelsize': 12,
    'axes.labelweight': 'bold',
    'xtick.labelsize': 11,
    'ytick.labelsize': 11,
    'figure.dpi': 300,           # Resolusi tinggi untuk cetak
    'axes.grid': True,
    'grid.alpha': 0.3,
    'grid.linestyle': '--',
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.edgecolor': '#333333',
    'text.color': '#333333',
    'axes.labelcolor': '#333333',
    'xtick.color': '#333333',
    'ytick.color': '#333333'
})

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STATS_FILE = os.path.join(BASE, "results", "network", "callbox_stats.json")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    if not os.path.exists(STATS_FILE):
        print(f"File {STATS_FILE} tidak ditemukan!")
        return

    with open(STATS_FILE, 'r') as f:
        data = json.load(f)

    packets_rx = data.get("packets_received", 0)
    packets_tx = data.get("packets_sent", 0)
    packets_drop = data.get("packets_dropped", 0)
    uptime = data.get("uptime", 0)
    avg_latency = data.get("avg_latency_ms", 0)
    bandwidth = data.get("current_bandwidth_mbps", 0)
    success = packets_tx - packets_drop
    
    pdr = 100.0
    if packets_tx > 0:
        pdr = (success / packets_tx) * 100

    # ---------------------------------------------------------
    # 1. GRAFIK BATANG HORIZONTAL (CLEAN & PROFESSIONAL)
    # ---------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = ['Packets Dropped', 'Packets Received', 'Packets Sent']
    values = [packets_drop, packets_rx, packets_tx]
    
    # Warna akademis: biru gelap dan abu-abu
    colors = ['#c0392b', '#2980b9', '#2c3e50'] 

    bars = ax.barh(labels, values, color=colors, height=0.6, edgecolor='black', linewidth=0.8)
    
    # Tambahkan angka di sebelah bar
    for bar in bars:
        width = bar.get_width()
        ax.text(width + (max(values)*0.02), bar.get_y() + bar.get_height()/2, 
                f"{int(width):,}", ha='left', va='center', fontsize=11)

    ax.set_xlabel('Total Packets', labelpad=10)
    ax.set_title('N3IWF Packet Transmission Statistics', pad=15)
    
    # Perpanjang sumbu X agar teks muat
    ax.set_xlim(0, max(values) * 1.2)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "Fig1_Packet_Statistics_Academic.png"), dpi=300)
    plt.close()

    # ---------------------------------------------------------
    # 2. DONUT CHART (LEBIH ELEGAN DARI PIE CHART)
    # ---------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6, 6))
    sizes = [success, packets_drop]
    labels_pie = [f'Success\n({pdr:.2f}%)', f'Dropped\n({(100-pdr):.2f}%)']
    colors_pie = ['#2980b9', '#e74c3c']
    explode = (0, 0.05) if packets_drop > 0 else (0, 0)
    
    wedges, texts, autotexts = ax.pie(
        sizes, explode=explode, labels=labels_pie, colors=colors_pie, 
        autopct='%1.2f%%', startangle=90, pctdistance=0.85,
        wedgeprops=dict(width=0.4, edgecolor='w', linewidth=2)
    )
    
    # Styling text
    for text in texts:
        text.set_fontsize(12)
        text.set_fontweight('bold')
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontsize(11)
        autotext.set_fontweight('bold')

    ax.set_title('Packet Delivery Rate (PDR)', pad=20)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "Fig2_PDR_DonutChart.png"), dpi=300)
    plt.close()

    # ---------------------------------------------------------
    # 3. TABEL SEBAGAI GAMBAR HIGH-RES (PAPER STYLE)
    # ---------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.axis('off')
    ax.axis('tight')

    table_data = [
        ['Network Parameter', 'Value'],
        ['Total Uptime', f"{uptime:,} Seconds"],
        ['Active Bandwidth', f"{bandwidth} Mbps"],
        ['Average Latency', f"{avg_latency:.2f} ms"],
        ['Total Packets Sent', f"{packets_tx:,}"],
        ['Total Packets Dropped', f"{packets_drop:,}"],
        ['Packet Delivery Rate', f"{pdr:.2f}%"]
    ]

    # Buat tabel
    table = ax.table(cellText=table_data, loc='center', cellLoc='left')
    
    # Styling tabel ala Paper/Jurnal
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.2, 1.8)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#bdc3c7')
        if row == 0:
            # Header styling
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#34495e')
            cell.set_edgecolor('#34495e')
        else:
            # Alternating row colors
            if row % 2 == 0:
                cell.set_facecolor('#f8f9f9')
            else:
                cell.set_facecolor('white')

    plt.title('N3IWF Network Summary', pad=20, fontweight='bold', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "Fig3_Network_Summary_Table.png"), dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Grafik bergaya akademis (High Res/300 DPI) telah dibuat di {OUT_DIR}")

if __name__ == "__main__":
    main()
