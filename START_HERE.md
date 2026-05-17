# 🚀 START HERE - Panduan Singkat

## 📖 File Penting (Baca Ini Aja!)

1. **`START_HERE.md`** ← Kamu di sini (1 menit)
2. **`DASHBOARD_ACCESS.md`** ← Cara akses dashboard (2 menit) ⭐
3. **`OUTPUT_RESULTS.md`** ← Apa aja hasilnya? (3 menit)
4. **`SINGLE_COMMAND_USAGE.md`** ← Panduan lengkap (5 menit)
5. **`README.md`** ← Overview project

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

---

## 📚 Baca Selanjutnya

- **Apa aja hasilnya?** `OUTPUT_RESULTS.md`
- **Detail lengkap:** `SINGLE_COMMAND_USAGE.md`
- **Troubleshooting:** `SINGLE_COMMAND_USAGE.md` (bagian Troubleshooting)
- **Project overview:** `README.md`

---

**That's it!** Simple kan? 🎉
