#ifndef PH_SENSOR_H
#define PH_SENSOR_H

#include <stdint.h>
#include "hardware/adc.h"

/* pH Sensor Module driver for Raspberry Pi Pico
 * Sensor output → ADC0 (GPIO26).
 * Calibration uses 2-point linear method matching slide results:
 *   pH 4.00 → 2.05448 V
 *   pH 6.86 → 1.54203 V
 *   pH 9.18 → 1.15793 V
 * All pH values returned as int32 × 1000 (e.g. 7015 = pH 7.015)
 * to avoid floating-point in hot path.
 */

#define PH_ADC_INPUT    0       /* ADC input index for GPIO26 */
#define PH_ADC_SAMPLES  16      /* oversampling count for noise reduction */

/* Calibration points stored as millivolts (integer) */
typedef struct {
    int32_t v1_mv;      /* voltage at cal point 1 (mV) */
    int32_t ph1_x1000;  /* pH at cal point 1 × 1000    */
    int32_t v2_mv;      /* voltage at cal point 2 (mV) */
    int32_t ph2_x1000;  /* pH at cal point 2 × 1000    */
} PhCalibration_t;

/* Default calibration from sensor measurements in the report */
extern const PhCalibration_t PH_CAL_DEFAULT;

/* Initialise ADC hardware for pH pin */
void ph_sensor_init(void);

/* Read averaged raw ADC (12-bit, 0–4095) */
uint16_t ph_sensor_read_raw(void);

/* Convert raw ADC → voltage in mV */
int32_t ph_adc_to_mv(uint16_t raw);

/* Convert voltage (mV) → pH × 1000 using provided calibration */
int32_t ph_mv_to_ph(int32_t mv, const PhCalibration_t *cal);

/* Convenience: read and return pH × 1000 */
int32_t ph_read(const PhCalibration_t *cal);

#endif /* PH_SENSOR_H */
