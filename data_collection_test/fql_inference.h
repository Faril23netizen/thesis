#ifndef FQL_INFERENCE_H
#define FQL_INFERENCE_H

#include <stdint.h>
#include <stdbool.h>

/*
 * FQL Inference — Raspberry Pi Pico WH (RP2040)
 * ================================================
 * Receives Q-table from RPi via USB Serial,
 * then runs FQL inference locally on the Pico.
 *
 * 25 rules × 4 actions = 100 float values (400 bytes)
 * State : (pH, Temperature)
 * Action: 0=OFF, 1=LOW, 2=MED, 3=HIGH
 *
 * pH fuzzy sets (5):
 *   VeryAcidic  [5.5, 5.5, 6.0, 6.5]
 *   Acidic      [5.5, 6.0, 6.5, 7.0]
 *   Normal      [6.5, 7.0, 7.5, 8.0]
 *   Alkaline    [7.5, 8.0, 8.5, 9.0]
 *   VeryAlkaline[8.5, 9.0, 9.5, 9.5]
 *
 * Temperature fuzzy sets (5):
 *   VeryCold  [17.5, 17.5, 18.0, 20.0]
 *   Cold      [18.0, 20.0, 22.0, 25.0]
 *   Optimal   [22.0, 25.0, 29.0, 32.0]
 *   Hot       [29.0, 32.0, 33.0, 34.5]
 *   VeryHot   [33.0, 34.0, 35.0, 35.0]
 *
 * Rule order: row-major (pH index * 5 + T index)
 *   Rule  0: VeryAcidic × VeryCold
 *   Rule  1: VeryAcidic × Cold
 *   ...
 *   Rule 24: VeryAlkaline × VeryHot
 */

/* ── Action constants ────────────────────────────────────────────────────── */
#define FQL_ACTION_OFF   0
#define FQL_ACTION_LOW   1
#define FQL_ACTION_MED   2
#define FQL_ACTION_HIGH  3
#define FQL_N_PH_SETS    5
#define FQL_N_T_SETS     5
#define FQL_N_RULES      25   /* 5 pH sets × 5 T sets */
#define FQL_N_ACTIONS    4

/* ── Q-table struct ─────────────────────────────────────────────────────── */
typedef struct {
    float q[FQL_N_RULES][FQL_N_ACTIONS];  /* 25×4 = 100 float = 400 bytes */
    bool  loaded;                          /* true after Q-table received */
} FQL_QTable_t;

/*
 * Parse Q-table string sent by RPi.
 * Format: "QTABLE:[[q00,q01,q02,q03],[q10,...],...]"
 * Returns true if all 100 values parsed successfully.
 */
bool fql_parse_qtable(const char *json_str, FQL_QTable_t *qt);

/*
 * Check USB input each loop iteration (non-blocking).
 * Reads lines from stdin; if line starts with "QTABLE:" -> parse and store.
 * Prints "ACK:QTABLE_LOADED" on success.
 */
void check_usb_input(FQL_QTable_t *qt);

/*
 * FQL inference: compute firing strengths for 25 rules,
 * return action with highest Q_FQL value.
 * ph_x1000 = pH × 1000 (integer), temp_x100 = T × 100 (integer)
 */
uint8_t fql_select_action(int32_t ph_x1000, int32_t temp_x100,
                           const FQL_QTable_t *qt);

#endif /* FQL_INFERENCE_H */
