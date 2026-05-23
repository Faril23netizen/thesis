# Pico WH Firmware - NH3 Risk Monitoring

Firmware untuk Raspberry Pi Pico WH - **MONITORING ONLY** (no aerator control).

## Features

- **Risk Assessment**: Rule-Based NH3 risk prediction
- **Sensor Reading**: pH (ADC0) + DS18B20 temperature (GPIO15)
- **WiFi Communication**: Send data to RPi5 via TCP (port 5005)
- **Q-Table Support**: Receive Q-table from RPi5 for FQL/DQN inference

## Hardware

```
Raspberry Pi Pico WH
├── GPIO26 (ADC0) → pH Sensor
├── GPIO15        → DS18B20 (1-Wire, pull-up 4.7kΩ)
└── LED (onboard) → Status indicator
```

## Protocol

**Pico → RPi5 (Data):**
```
DATA:ph_x1000,temp_x100,risk\n
```
Example: `DATA:7250,2850,1\n`
- pH = 7.250
- T = 28.50°C
- Risk = 1 (CAUTION)

**RPi5 → Pico (Q-table):**
```
QTABLE:[[q00,q01,q02,q03],[q10,...],...]\n
```

**Pico → RPi5 (ACK):**
```
ACK:QTABLE_LOADED\n
```

## Risk Levels

```c
#define RISK_SAFE       0  // NH3 < 1%
#define RISK_CAUTION    1  // NH3 1-5%
#define RISK_WARNING    2  // NH3 5-10%
#define RISK_CRITICAL   3  // NH3 > 10%
```

## Build

```bash
cd pico_firmware
mkdir build && cd build
cmake ..
make -j4
```

Output: `aquaculture_monitoring.uf2`

## Flash

1. Hold BOOTSEL button on Pico WH
2. Connect USB to computer
3. Copy `aquaculture_monitoring.uf2` to RPI-RP2 drive
4. Pico will auto-reboot with new firmware

## WiFi Configuration

Edit in `main.c`:
```c
#define WIFI_SSID       "N3IWF_AQUA"
#define WIFI_PASSWORD   "aquaculture2026"
#define SERVER_IP       "10.42.0.1"
#define SERVER_PORT     5005
```

## Files

```
pico_firmware/
├── main.c              # Main program (monitoring loop)
├── ph_sensor.h/c       # pH sensor driver (ADC)
├── ds18b20.h/c         # DS18B20 temperature driver (1-Wire)
├── fql_inference.h/c   # FQL Q-table inference engine
├── CMakeLists.txt      # Build configuration
└── README.md           # This file
```

## Monitoring Output

```
========================================
  Pico WH - NH3 Risk Monitoring
  MONITORING ONLY (No Control)
========================================
# Connecting to WiFi: N3IWF_AQUA
# WiFi connected!
# Connecting to 10.42.0.1:5005
# TCP connected!
# System ready - starting monitoring
> #0001 | pH=7.250 T=28.5°C NH3=0.123% | Risk=SAFE
> #0002 | pH=7.180 T=28.7°C NH3=0.145% | Risk=SAFE
> #0003 | pH=8.120 T=29.2°C NH3=1.234% | Risk=CAUTION
```

## Notes

- **No aerator control** - monitoring only
- **Risk-based** instead of action-based
- Compatible with RPi5 Python code (FQL/DQN training)
- LED blinks on each data transmission
