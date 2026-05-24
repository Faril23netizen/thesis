#!/usr/bin/env python3
import os
import sys
import time
import socket
import json
import subprocess

def check_port_5000():
    try:
        # Pengecekan port 5000 menggunakan socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = s.connect_ex(('127.0.0.1', 5000))
        s.close()
        if result == 0:
            return True, "Port 5000 TERBUKA dan merespon (Server menyala)"
        else:
            return False, "Port 5000 TERTUTUP (Pico WH tidak punya tempat untuk terhubung!)"
    except Exception as e:
        return False, f"Error cek port: {e}"

def check_state_json():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state_file = os.path.join(base_dir, "results", "hasil_real", "state.json")
    
    if not os.path.exists(state_file):
        return False, "File state.json BELUM ADA (Pico WH belum mengirimkan data apapun)"
        
    try:
        file_age = time.time() - os.path.getmtime(state_file)
        with open(state_file, 'r') as f:
            data = json.load(f)
            
        status = f"File state.json ADA (diperbarui {file_age:.1f} detik yang lalu)."
        if file_age > 30:
            status += "\n   ⚠️ WARNING: Data sudah usang! Pico WH mungkin terputus."
        else:
            status += "\n   ✅ Data segar. Pico WH sedang aktif mengirim data."
            
        return True, status
    except Exception as e:
        return False, f"Error membaca state.json: {e}"

def main():
    print("="*60)
    print("🔍 DIAGNOSTIK KONEKSI PICO WH & DASHBOARD")
    print("="*60)
    
    # 1. Cek Server Port 5000
    print("\n[1] Mengecek TCP Server (run_real.py)...")
    is_open, msg = check_port_5000()
    print(f"    {msg}")
    
    # 2. Cek Data Sensor
    print("\n[2] Mengecek aliran data sensor (state.json)...")
    has_data, msg2 = check_state_json()
    print(f"    {msg2}")
    
    print("\n" + "="*60)
    if is_open and has_data:
        print("💡 KESIMPULAN: Sistem normal. Jika grafik di web blank, tekan CTRL+F5 di browser Anda.")
    elif is_open and not has_data:
        print("💡 KESIMPULAN: Server Siap, tapi PICO BELUM KONEK. Cabut-pasang kabel power Pico WH Anda.")
    elif not is_open:
        print("💡 KESIMPULAN: SERVER MATI! Coba matikan semua (sudo ./stop_all.sh) lalu nyalakan lagi (sudo ./start_all.sh).")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
