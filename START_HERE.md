# 🚀 START HERE - Panduan Singkat

## 📖 Dokumentasi (3 File Aja!)

1. **`START_HERE.md`** ← Panduan singkat (2 menit)
2. **`SINGLE_COMMAND_USAGE.md`** ← Manual lengkap (5 menit)
3. **`OUTPUT_RESULTS.md`** ← Hasil analisis (3 menit)

**Sisanya:** File teknis (ga perlu dibaca)

---

## ⚡ Cara Pakai (3 Command)

```bash
# 1. Start semua
sudo ./start_all.sh

# 2. Buka dashboard
http://10.42.0.1:5000

# 3. Stop dan analisis (besok pagi)
sudo ./stop_all.sh
python3 analyze_all.py
```

---

## ✅ Sebelum Start

```bash
# Install dependencies
sudo apt install -y strongswan strongswan-pki libcharon-extra-plugins
pip3 install flask numpy matplotlib

# Make executable
chmod +x start_all.sh stop_all.sh

# Check network
ping 10.42.0.206  # Pico harus connect
```

---

## 📊 Hasil

Setelah `python3 analyze_all.py`:

- **PDF:** `results/thesis/complete_analysis.pdf` ⭐
- **CSV:** `results/thesis/summary.csv`
- **Plots:** `results/thesis/plots/*.png`

---

## 🐛 Masalah?

**Pico ga connect:**
```bash
ping 10.42.0.206
```

**Dashboard ga bisa dibuka:**
```bash
sudo ufw allow 5000/tcp
```

**IPsec error:**
```bash
sudo ipsec restart
```

**Restart semua:**
```bash
sudo ./stop_all.sh
sleep 5
sudo ./start_all.sh
```

**RPi5 dimatikan tanpa stop:**
```bash
# Quick restart (otomatis bersihkan)
chmod +x quick_restart.sh
sudo ./quick_restart.sh
```

---

## 📚 Baca Selanjutnya

- **Detail lengkap:** `SINGLE_COMMAND_USAGE.md`
- **Apa aja hasilnya?** `OUTPUT_RESULTS.md`
- **Project overview:** `README.md`

---

**That's it!** Simple kan? 🎉
