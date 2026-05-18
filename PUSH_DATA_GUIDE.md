# 📤 Push Data dari RPi5 ke GitHub

## 🎯 Tujuan

Push file hasil data dari RPi5 ke GitHub supaya bisa dianalisa di Windows.

---

## 🚀 Di RPi5

```bash
# 1. Make script executable
chmod +x push_data.sh

# 2. Push data ke GitHub
./push_data.sh
```

Script akan otomatis:
- ✅ Check file data ada
- ✅ Stage file hasil (comparison.csv, network stats)
- ✅ Commit dengan timestamp
- ✅ Push ke GitHub

---

## 💻 Di Windows

```bash
# 1. Pull data dari GitHub
git pull

# 2. Filter data (hanya sampai step 10000)
python filter_data.py --max-total-steps 10000

# 3. Backup original
cp results/hasil_real/comparison.csv results/hasil_real/comparison.csv.backup

# 4. Gunakan data filtered
cp results/hasil_real/comparison_filtered.csv results/hasil_real/comparison.csv

# 5. Generate grafik
python analyze_all.py
```

---

## 📊 File yang Di-Push

- `results/hasil_real/comparison.csv` - Raw data (RB + FQL + DQN)
- `results/hasil_real/comparison_filtered.csv` - Filtered data (jika ada)
- `results/network/callbox_stats.json` - Network stats
- `results/network/n3iwf_status.json` - N3IWF status

---

## 🔄 Workflow

```
RPi5 (Data Collection)
    ↓
    ./push_data.sh
    ↓
GitHub (Storage)
    ↓
    git pull
    ↓
Windows (Analysis)
    ↓
    python analyze_all.py
    ↓
Grafik + Excel
```

---

## ⚠️ Notes

- File log (`.log`) tidak di-push (terlalu besar)
- File hasil analisis (`.png`, `.xlsx`) tidak di-push (generate di Windows)
- Hanya raw data yang di-push untuk analisis

---

## 🐛 Troubleshooting

**Error: "comparison.csv not found"**
```bash
# Cek apakah file ada
ls -lh results/hasil_real/comparison.csv
```

**Error: "Permission denied"**
```bash
chmod +x push_data.sh
```

**Error: "Git push failed"**
```bash
# Setup git credentials
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

---

**Ready!** Sekarang data bisa di-push dari RPi5 dan dianalisa di Windows. 🚀
