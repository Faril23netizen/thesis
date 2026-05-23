#include "ds18b20.h"
#include <stdio.h>
#include "hardware/gpio.h"
#include "pico/stdlib.h"

/* ── 1-Wire timing constants (µs) ───────────────────────────────────────── */
#define OW_RESET_PULSE_US   480
#define OW_RESET_WAIT_US    70
#define OW_RESET_RELEASE_US 410
#define OW_WRITE1_LOW_US    6
#define OW_WRITE1_HIGH_US   64
#define OW_WRITE0_LOW_US    60
#define OW_WRITE0_HIGH_US   10
#define OW_READ_LOW_US      6
#define OW_READ_SAMPLE_US   9
#define OW_READ_HIGH_US     55

/* ── DS18B20 ROM / function commands ────────────────────────────────────── */
#define CMD_SEARCH_ROM      0xF0
#define CMD_READ_ROM        0x33
#define CMD_SKIP_ROM        0xCC
#define CMD_CONVERT_T       0x44
#define CMD_READ_SCRATCHPAD 0xBE

/* ── Low-level 1-Wire primitives ────────────────────────────────────────── */

static inline void ow_pin_low(uint pin) {
    gpio_set_dir(pin, GPIO_OUT);
    gpio_put(pin, 0);
}

static inline void ow_pin_release(uint pin) {
    gpio_set_dir(pin, GPIO_IN);   /* external pull-up brings line high */
}

static inline bool ow_pin_read(uint pin) {
    return gpio_get(pin);
}

static bool ow_reset(uint pin) {
    /* Pull low for reset pulse */
    ow_pin_low(pin);
    sleep_us(OW_RESET_PULSE_US);
    ow_pin_release(pin);
    sleep_us(OW_RESET_WAIT_US);

    /* Sample presence pulse (sensor pulls low) */
    bool presence = !ow_pin_read(pin);
    sleep_us(OW_RESET_RELEASE_US);
    return presence;
}

static void ow_write_bit(uint pin, bool bit) {
    if (bit) {
        ow_pin_low(pin);
        sleep_us(OW_WRITE1_LOW_US);
        ow_pin_release(pin);
        sleep_us(OW_WRITE1_HIGH_US);
    } else {
        ow_pin_low(pin);
        sleep_us(OW_WRITE0_LOW_US);
        ow_pin_release(pin);
        sleep_us(OW_WRITE0_HIGH_US);
    }
}

static void ow_write_byte(uint pin, uint8_t byte) {
    for (int i = 0; i < 8; i++) {
        ow_write_bit(pin, (byte >> i) & 0x01);
    }
}

static bool ow_read_bit(uint pin) {
    ow_pin_low(pin);
    sleep_us(OW_READ_LOW_US);
    ow_pin_release(pin);
    sleep_us(OW_READ_SAMPLE_US);
    bool bit = ow_pin_read(pin);
    sleep_us(OW_READ_HIGH_US);
    return bit;
}

static uint8_t ow_read_byte(uint pin) {
    uint8_t byte = 0;
    for (int i = 0; i < 8; i++) {
        if (ow_read_bit(pin)) byte |= (1 << i);
    }
    return byte;
}

/* ── CRC-8 (Dallas/Maxim) ───────────────────────────────────────────────── */
static uint8_t crc8(const uint8_t *data, size_t len) {
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        uint8_t byte = data[i];
        for (int j = 0; j < 8; j++) {
            uint8_t mix = (crc ^ byte) & 0x01;
            crc >>= 1;
            if (mix) crc ^= 0x8C;
            byte >>= 1;
        }
    }
    return crc;
}

/* ── Public API ─────────────────────────────────────────────────────────── */

bool ds18b20_init(DS18B20_t *dev, uint gpio_pin) {
    dev->gpio_pin = gpio_pin;
    dev->found    = false;

    gpio_init(gpio_pin);
    gpio_pull_up(gpio_pin);     /* internal pull-up ~50kΩ, cukup untuk kabel pendek */
    ow_pin_release(gpio_pin);   /* start in input mode */
    sleep_ms(1);

    if (!ow_reset(gpio_pin)) return false;

    /* READ ROM command — works only when exactly one sensor is on the bus */
    ow_write_byte(gpio_pin, CMD_READ_ROM);
    for (int i = 0; i < 8; i++) {
        dev->rom[i] = ow_read_byte(gpio_pin);
    }

    /* Validate CRC */
    if (crc8(dev->rom, 7) != dev->rom[7]) return false;
    if (dev->rom[0] != 0x28) return false;   /* 0x28 = DS18B20 family code */

    dev->found = true;
    return true;
}

void ds18b20_convert(DS18B20_t *dev) {
    ow_reset(dev->gpio_pin);
    ow_write_byte(dev->gpio_pin, CMD_SKIP_ROM);
    ow_write_byte(dev->gpio_pin, CMD_CONVERT_T);
    /* Line must be kept high (pull-up supplies power) during conversion */
    ow_pin_release(dev->gpio_pin);
}

int32_t ds18b20_read_raw(DS18B20_t *dev) {
    ow_reset(dev->gpio_pin);
    ow_write_byte(dev->gpio_pin, CMD_SKIP_ROM);
    ow_write_byte(dev->gpio_pin, CMD_READ_SCRATCHPAD);

    uint8_t sp[9];
    for (int i = 0; i < 9; i++) {
        sp[i] = ow_read_byte(dev->gpio_pin);
    }

    /* Verify scratchpad CRC */
    if (crc8(sp, 8) != sp[8]) return INT32_MIN;

    /* DS18B20 12-bit: LSByte + MSByte, LSB = 0.0625°C */
    int16_t raw = (int16_t)((sp[1] << 8) | sp[0]);
    /* Convert to °C × 100: raw × 6.25 */
    return (int32_t)raw * 625 / 100;
}

int32_t ds18b20_read_blocking(DS18B20_t *dev) {
    ds18b20_convert(dev);
    sleep_ms(750);          /* 12-bit conversion time */
    return ds18b20_read_raw(dev);
}
