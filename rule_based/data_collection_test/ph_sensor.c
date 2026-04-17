#include "ph_sensor.h"
#include "pico/stdlib.h"
#include "hardware/adc.h"
#include "hardware/gpio.h"

/* ── Default 2-point calibration (from lab results in report) ───────────── */
const PhCalibration_t PH_CAL_DEFAULT = {
    .v1_mv      = 2054,   /* 2.05448 V → 2054 mV  (pH 4.00) */
    .ph1_x1000  = 4000,
    .v2_mv      = 1542,   /* 1.54203 V → 1542 mV  (pH 6.86) */
    .ph2_x1000  = 6860,
};

/* ── ADC constants ──────────────────────────────────────────────────────── */
#define ADC_VREF_MV     3300    /* RP2040 ADC reference = 3.3 V */
#define ADC_MAX_COUNT   4095    /* 12-bit */
#define ADC_GPIO_PIN    26      /* GPIO26 = ADC0 */

/* ── Public API ─────────────────────────────────────────────────────────── */

void ph_sensor_init(void) {
    adc_init();
    adc_gpio_init(ADC_GPIO_PIN);
    adc_select_input(PH_ADC_INPUT);
}

uint16_t ph_sensor_read_raw(void) {
    uint32_t sum = 0;
    for (int i = 0; i < PH_ADC_SAMPLES; i++) {
        sum += adc_read();
        sleep_us(200);
    }
    return (uint16_t)(sum / PH_ADC_SAMPLES);
}

int32_t ph_adc_to_mv(uint16_t raw) {
    /* voltage_mV = raw × 3300 / 4095 */
    return (int32_t)raw * ADC_VREF_MV / ADC_MAX_COUNT;
}

int32_t ph_mv_to_ph(int32_t mv, const PhCalibration_t *cal) {
    /*
     * Linear interpolation:
     *   pH = pH1 + (V - V1) × (pH2 - pH1) / (V2 - V1)
     * All values scaled × 1000 to keep integer arithmetic.
     * Numerator: (mv - v1_mv) × (ph2 - ph1)   [units: mV × pH_units×1000]
     * Denominator: (v2_mv - v1_mv)              [units: mV]
     * Result: pH × 1000
     */
    int32_t dv   = cal->v2_mv - cal->v1_mv;          /* negative: V drops with pH */
    int32_t dph  = cal->ph2_x1000 - cal->ph1_x1000;  /* positive */
    int32_t ph   = cal->ph1_x1000 + (mv - cal->v1_mv) * dph / dv;
    return ph;
}

int32_t ph_read(const PhCalibration_t *cal) {
    uint16_t raw = ph_sensor_read_raw();
    int32_t  mv  = ph_adc_to_mv(raw);
    return ph_mv_to_ph(mv, cal);
}
