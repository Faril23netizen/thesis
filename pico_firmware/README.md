# Pico WH Firmware - NH3 Risk Monitoring

Firmware untuk Raspberry Pi Pico WH - **MONITORING ONLY** (no aerator control).

## Features

- **Risk Assessment**: Rule-Based NH3 risk calculation
- **Sensor Reading**: pH (ADC0) + DS18B20 temperature (GPIO15)
- **WiFi Communication**: Send data to RPi5 via TCP (port 5000)

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

## Risk Levels

Based on NH3% calculation:
```c
#define RISK_SAFE       0  // NH3 < 1%
#define RISK_CAUTION    1  // NH3 1-5%
#define RISK_WARNING    2  // NH3 5-10%
#define RISK_CRITICAL   3  // NH3 > 10%
```

## Build (Windows)

```bash
cd pico_firmware
mkdir build
cd build
cmake -G "NMake Makefiles" ..
nmake
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
#define SERVER_PORT     5000
```

## Files

```
pico_firmware/
├── main.c              # Main program (monitoring loop)
├── ph_sensor.h/c       # pH sensor driver (ADC)
├── ds18b20.h/c         # DS18B20 temperature driver (1-Wire)
├── CMakeLists.txt      # Build configuration
└── README.md           # This file
```

## Monitoring Output

```
=== Pico WH Aquaculture Monitor ===
Connecting to WiFi: N3IWF_AQUA
WiFi connected
Sensors initialized
Starting monitoring loop...
Connected to server
pH: 7.25, Temp: 28.50°C, Risk: 0
Sent: DATA:7250,2850,0
pH: 7.18, Temp: 28.70°C, Risk: 0
Sent: DATA:7180,2870,0
```

## Notes

- **No aerator control** - monitoring only
- **Risk-based** instead of action-based
- Reads sensors every 5 seconds
- LED blinks on WiFi activity
