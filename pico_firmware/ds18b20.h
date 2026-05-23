#ifndef DS18B20_H
#define DS18B20_H

#include <stdint.h>
#include <stdbool.h>
#include "pico/stdlib.h"

/* DS18B20 1-Wire driver for Raspberry Pi Pico
 * GPIO pin is configurable via ds18b20_init().
 * Resolution fixed at 12-bit → conversion time ~750 ms.
 */

typedef struct {
    uint gpio_pin;
    uint8_t rom[8];     /* 64-bit ROM code of detected sensor */
    bool    found;
} DS18B20_t;

/* Initialise and scan for sensor on given GPIO.
 * Returns true if at least one sensor is found.
 * External 4.7 kΩ pull-up required on the data line. */
bool ds18b20_init(DS18B20_t *dev, uint gpio_pin);

/* Trigger a temperature conversion (non-blocking start).
 * Caller must wait at least 750 ms before reading. */
void ds18b20_convert(DS18B20_t *dev);

/* Read converted temperature in °C (×100 as integer to avoid float printf).
 * E.g. 2501 = 25.01 °C.
 * Call at least 750 ms after ds18b20_convert(). */
int32_t ds18b20_read_raw(DS18B20_t *dev);   /* returns temp_c × 100 */

/* Helper: blocking read — triggers conversion, waits, then reads. */
int32_t ds18b20_read_blocking(DS18B20_t *dev);

#endif /* DS18B20_H */
