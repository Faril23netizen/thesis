# Pico WH Firmware - Aquaculture Monitoring

Firmware untuk Raspberry Pi Pico WH dengan WiFi untuk sistem monitoring aquaculture.

**IMPORTANT**: Firmware ini sudah di-flash ke Pico WH. Kode Rule-Based berjalan di Pico, bukan di RPi5.

## Features

- **Rule-Based Controller**: Logic sederhana berbasis threshold pH dan suhu (berjalan di Pico)
- **Sensor Reading**: Baca pH (ADC0/GPIO26) dan DS18B20 temperature (GPIO15)
- **WiFi Communication**: Kirim data ke RPi5 via N3IWF tunnel (TCP port 5005)
- **Q-Table Support**: Terima Q-table dari RPi5 untuk FQL/DQN inference
- **Progressive Learning**: Rule-Based → FQL → DQN

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PICO WH (RP2040 + WiFi)                                    │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ pH Sensor  │  │  DS18B20     │  │  Relay       │        │
│  │ (ADC0)     │  │  (GPIO15)    │  │  (GPIO16/17) │        │
│  └─────┬──────┘  └──────┬───────┘  └──────▲───────┘        │
│        │                │                  │                │
│        └────────┬───────┘                  │                │
│                 ▼                          │                │
│         ┌───────────────┐                  │                │
│         │ Rule-Based    │──────────────────┘                │
│         │ safety_action │ (ALWAYS ACTIVE)                   │
│         └───────┬───────┘                                   │
│                 │                                            │
│                 ▼                                            │
│         ┌───────────────┐                                   │
│         │ FQL Inference │ (if Q-table loaded)               │
│         │ (optional)    │                                   │
│         └───────┬───────┘                                   │
│                 │                                            │
│                 ▼                                            │
│         ┌───────────────┐                                   │
│         │ WiFi TCP      │                                   │
│         │ Send DATA     │                                   │
│         └───────┬───────┘                                   │
└─────────────────┼───────────────────────────────────────────┘
                  │ N3IWF Tunnel (WiFi)
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  RPI5 (N3IWF Server)                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ FQL Agent    │  │ DQN Agent    │  │ Dashboard    │      │
│  │ (Training)   │  │ (Training)   │  │ (Flask)      │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                 │                                 │
│         └────────┬────────┘                                 │
│                  ▼                                           │
│          ┌───────────────┐                                  │
│          │ Send Q-table  │                                  │
│          │ to Pico       │                                  │
│          └───────────────┘                                  │
└─────────────────────────────────────────────────────────────┘
```

## Hardware Requirements

- Raspberry Pi Pico WH (RP2040 + CYW43 WiFi)
- pH sensor (analog output → GPIO26/ADC0)
- Temperature sensor (analog output → GPIO27/ADC1)
- Power supply (5V via USB atau external)

## Pin Configuration

```
GPIO26 (ADC0) → pH Sensor
GPIO27 (ADC1) → Temperature Sensor
LED (onboard) → Status indicator
```

## Build Instructions

### Prerequisites

1. Install Pico SDK:
```bash
cd ~
git clone https://github.com/raspberrypi/pico-sdk.git
cd pico-sdk
git submodule update --init
export PICO_SDK_PATH=~/pico-sdk
```

2. Install build tools:
```bash
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential
```

### Build Firmware

```bash
cd pico_firmware
mkdir build
cd build
cmake ..
make
```

Output: `aquaculture.uf2`

### Flash to Pico WH

1. Hold BOOTSEL button on Pico WH
2. Connect USB cable to computer
3. Pico akan muncul sebagai USB drive
4. Copy `aquaculture.uf2` ke drive tersebut
5. Pico akan auto-reboot dengan firmware baru

## WiFi Configuration

Edit di `main.c`:

```c
#define WIFI_SSID       "N3IWF_AQUA"           // Ganti dengan SSID RPi5
#define WIFI_PASSWORD   "aquaculture2026"      // Ganti dengan password
#define SERVER_IP       "10.42.0.1"            // IP RPi5
#define SERVER_PORT     5005                   // Port N3IWF
```

## Protocol

### Data Format (Pico → RPi5)

```
DATA:ph_x1000,temp_x100,action\n
```

Example:
```
DATA:7250,2850,1\n
```
- pH = 7.250
- T = 28.50°C
- Action = 1 (LOW)

### Q-Table Format (RPi5 → Pico)

```
QTABLE:[[q00,q01,q02,q03],[q10,q11,q12,q13],...]\n
```

### ACK Response (Pico → RPi5)

```
ACK:QTABLE_LOADED\n
```

## Rule-Based Logic

```c
int safety_action(float pH, float T) {
    // CRITICAL: pH < 6.0 or pH > 9.5 or T > 35°C
    if (pH < 6.0f || pH > 9.5f || T > 35.0f) {
        return ACTION_HIGH;  // 3
    }
    
    // WARNING: pH < 6.5 or pH > 8.5 or T > 30°C
    if (pH < 6.5f || pH > 8.5f || T > 30.0f) {
        return ACTION_MED;   // 2
    }
    
    // NORMAL
    return ACTION_LOW;       // 1
}
```

## Monitoring

Connect via USB serial (115200 baud):

```bash
screen /dev/ttyACM0 115200
```

Output:
```
========================================
  Pico WH Aquaculture Firmware
  Rule-Based + FQL/DQN
========================================
> Connecting to WiFi: N3IWF_AQUA
> WiFi connected!
> Connecting to server: 10.42.0.1:5005
> Server connected!
> System ready - starting monitoring
> Mode: Rule-Based (will upgrade to FQL/DQN when Q-table received)
# pH=7.250 T=28.5°C Action=1 (RB)
> Sending: DATA:7250,2850,1
# pH=7.180 T=28.7°C Action=1 (RB)
> Sending: DATA:7180,2870,1
```

## Troubleshooting

**WiFi tidak connect:**
- Cek SSID dan password
- Pastikan RPi5 hotspot aktif
- Cek jarak antara Pico dan RPi5

**Sensor tidak terbaca:**
- Cek koneksi ADC pin
- Cek power supply sensor
- Kalibrasi sensor (edit conversion formula di `read_ph_sensor()` dan `read_temp_sensor()`)

**Server tidak connect:**
- Cek IP address RPi5
- Pastikan N3IWF server running di RPi5
- Cek firewall: `sudo ufw allow 5005/tcp`

## Development

Untuk development, gunakan Pico Debug Probe atau printf debugging via USB serial.

## License

MIT License - Free to use for thesis and research.
