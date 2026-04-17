# Data Collection Capacity Test — RP2040 Pico

**Thesis:** Edge-Intelligent Aquaculture Aerator Control Using Progressive Hybrid FQL-DQN with N3IWF LES  
**Author:** Faril Pirwanhadi (M14128104)

Firmware ini mengukur kapasitas penyimpanan data sensor (pH, Suhu, NH3) di SRAM RP2040 (264 KB) dan menguji throughput pembacaan sensor.

---

## Wiring Diagram

```
                        Raspberry Pi Pico (RP2040)
                       ┌─────────────────────────┐
                       │                         │
    pH Sensor Module   │  GPIO26 (ADC0) ◄────────┼──── OUT/Signal
    ┌──────────────┐   │  3V3 (pin 36)  ─────────┼──── VCC
    │  pH Electrode│   │  GND           ─────────┼──── GND
    │  + BNC Probe │   │                         │
    └──────────────┘   │                         │
                       │                         │
                       │  GPIO15        ◄────────┼──┬── DATA
                       │  3V3 (pin 36)  ─────────┼──┤── VDD (3.3V)
                       │                         │  │   DS18B20
                       │  GND           ─────────┼──┴── GND
                       │                         │
                       │  GPIO25 (LED)  ──────[LED onboard]
                       │                         │
                       │  USB (UART)    ──────────┼──── PC / Serial Monitor
                       └─────────────────────────┘
                                 │
                              [4.7 kΩ]  ← pull-up resistor
                                 │
                              3V3 ─────────────────────── DATA line DS18B20
```

### Detail Koneksi

| Komponen        | Pin Komponen | Pin Pico           | Keterangan                       |
|-----------------|--------------|---------------------|----------------------------------|
| pH Sensor Module | VCC          | 3V3 (pin 36)        | Supply 3.3 V                     |
| pH Sensor Module | GND          | GND (pin 38)        |                                  |
| pH Sensor Module | OUT / Signal | GPIO26 (ADC0)       | Analog output 0–3.3 V            |
| DS18B20          | VDD          | 3V3 (pin 36)        | Supply 3.3 V                     |
| DS18B20          | GND          | GND (pin 38)        |                                  |
| DS18B20          | DATA         | GPIO15              | 1-Wire, butuh pull-up 4.7 kΩ     |
| Resistor 4.7 kΩ  | —            | GPIO15 ↔ 3V3        | Pull-up wajib untuk 1-Wire       |
| Onboard LED      | —            | GPIO25              | Blink saat test selesai          |
| USB              | —            | USB Micro           | Serial output 115200 baud        |

> **Catatan:** DS18B20 menggunakan protokol 1-Wire. Pull-up 4.7 kΩ dari DATA ke 3.3 V adalah **wajib** — sensor tidak akan terdeteksi tanpanya.

---

## Arsitektur Software

```
main.c
│
├── ph_sensor.h / ph_sensor.c
│   ├── ph_sensor_init()        → inisialisasi ADC pada GPIO26
│   ├── ph_sensor_read_raw()    → rata-rata 16 sampel ADC (12-bit, 0–4095)
│   ├── ph_adc_to_mv()          → raw ADC → tegangan (mV)
│   └── ph_mv_to_ph()           → tegangan (mV) → pH × 1000
│       └── Kalibrasi 2 titik:
│           pH 4.00 → 2054 mV
│           pH 6.86 → 1542 mV
│
├── ds18b20.h / ds18b20.c
│   ├── ds18b20_init()          → scan sensor via 1-Wire, validasi ROM + CRC
│   ├── ds18b20_convert()       → trigger konversi suhu (non-blocking)
│   └── ds18b20_read_raw()      → baca scratchpad, validasi CRC → °C × 100
│       └── Protokol 1-Wire: reset → skip ROM → convert T / read scratchpad
│
└── main()
    ├── Inisialisasi sensor
    ├── Loop per 1000 ms:
    │   ├── ds18b20_convert()       ← mulai konversi (750 ms)
    │   ├── ph_sensor_read_raw()    ← baca pH sambil nunggu DS18B20 (~5 ms)
    │   ├── sleep sisa waktu (~755 ms)
    │   ├── ds18b20_read_raw()      ← baca suhu
    │   ├── calc_nh3_x100000()      ← hitung fraksi NH3 bebas
    │   ├── safety_check()          ← rule-based status
    │   └── simpan → records[]      ← buffer SRAM
    └── print_summary()             → statistik akhir via USB Serial
```

---

## Alur Data

```
GPIO26 (ADC0)
     │
     ▼
[pH Sensor ADC]
 16x oversampling
 12-bit (0–4095)
     │ adc_raw
     ▼
[ph_adc_to_mv()]
 raw × 3300 / 4095
     │ ph_mv (mV)
     ▼
[ph_mv_to_ph()]
 linear interpolasi 2-titik
     │ ph_x1000
     │
     │            GPIO15 (1-Wire)
     │                 │
     │                 ▼
     │          [DS18B20 Driver]
     │          1-Wire protocol
     │          CRC-8 validated
     │                 │ temp_x100
     │                 │
     ▼                 ▼
[calc_nh3_x100000()]──────────────
 pKa(T) = 0.09018 + 2729.92/(T+273.15)
 fNH3 = 1 / (1 + 10^(pKa - pH))
     │ nh3_x100000
     │
     ▼
[safety_check()]
 pH < 6.0 atau > 9.5  → DANGER_PH  (2)
 T > 35°C             → DANGER_TEMP (3)
 6.0 ≤ pH ≤ 9.5, T ≤ 35 tapi di luar safe zone → WARNING (1)
 6.5 ≤ pH ≤ 8.5, T ≤ 30 → SAFE (0)
     │ status
     │
     ▼
┌────────────────────┐
│   SensorRecord_t   │ ← 20 bytes/record
│  timestamp_ms  4B  │
│  ph_x1000      4B  │
│  temp_x100     4B  │
│  nh3_x100000   4B  │
│  adc_raw       2B  │
│  status        1B  │
│  _pad          1B  │
└────────────────────┘
     │
     ▼
records[2000]           ← static buffer, 40 KB dari 264 KB SRAM
     │
     ▼
USB Serial (115200 baud) → PC / Terminal
```

---

## Struktur File

```
data_collection_test/
├── CMakeLists.txt          # Build config Pico SDK
├── pico_sdk_import.cmake   # Import Pico SDK
├── main.c                  # Program utama, loop sampling, NH3, safety check
├── ph_sensor.h / .c        # Driver ADC pH sensor (GPIO26)
└── ds18b20.h / .c          # Driver 1-Wire DS18B20 (GPIO15)
```

---

## Cara Build & Flash

```bash
mkdir build && cd build
cmake ..
make -j4
# Hasilnya: data_collection_test.uf2

# Flash ke Pico:
# 1. Tekan tombol BOOTSEL sambil colok USB
# 2. Pico muncul sebagai USB drive (RPI-RP2)
# 3. Copy file .uf2 ke drive tersebut
```

---

## Output Serial

Sambungkan ke serial monitor (115200 baud). Contoh output:

```
================================================================
  DATA COLLECTION CAPACITY TEST — RP2040 Pico
  sizeof(SensorRecord_t) = 20 bytes
  Buffer size            = 40000 bytes (39.1 KB)
  Sample interval        = 1000 ms
  Max records            = 2000
================================================================

  #    | Time(s) |   pH   | Temp°C | NH3%    | ADC  | FreeRAM | Status
-------|---------|--------|--------|---------|------|---------|------------
    1 |     1.0 | 7.015  | 25.01  | 0.123%  | 1912 | 180K    | SAFE
    2 |     2.0 | 7.020  | 25.03  | 0.125%  | 1910 |  178K   | SAFE
  ...

================================================================
  RINGKASAN TEST
  Total records : 2000
  Durasi total  : 2000000 ms
  Estimasi kapasitas SRAM 264 KB:
    50% SRAM (132 KB) → ~6710 records
    70% SRAM (185 KB) → ~9404 records
================================================================
```

---

## Catatan Desain

- **Fixed-point arithmetic**: semua nilai sensor disimpan sebagai integer (pH×1000, °C×100, NH3×100000) untuk menghindari float di hot path
- **NH3 calculation**: menggunakan `float` hanya untuk kalkulasi NH3 (bukan hot path inference) — dipanggil sekali per detik
- **Oversampling pH**: 16 sampel ADC dirata-rata untuk mengurangi noise analog
- **DS18B20 non-blocking**: `ds18b20_convert()` dimulai bersamaan dengan pembacaan pH untuk memaksimalkan throughput (parallel ~5ms pH read + 750ms DS18B20 wait)
- **Memory guard**: estimasi free RAM via malloc probe; berhenti otomatis jika < 10 KB tersisa
