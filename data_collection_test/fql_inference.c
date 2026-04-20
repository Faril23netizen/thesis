/*
 * FQL Inference — Implementation
 * ================================
 * Thesis : Edge-Intelligent Aquaculture Aerator Control
 *          Using Progressive Hybrid FQL-DQN with N3IWF LES
 * Student: Faril Pirwanhadi (M14128104)
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "fql_inference.h"
#include "pico/stdlib.h"

/* ── USB serial receive buffer ──────────────────────────────────────────── */
/* Must fit the full QTABLE string: 25 rules × 4 actions × ~8 chars ≈ 900 bytes */
#define USB_BUF_SIZE  1200
static char  _usb_buf[USB_BUF_SIZE];
static int   _usb_pos = 0;

/* ── Trapezoidal membership function ────────────────────────────────────── */
static float trapezoid(float x, float a, float b, float c, float d) {
    if (x <= a || x >= d) return 0.0f;
    if (x >= b && x <= c) return 1.0f;
    if (x < b)            return (x - a) / (b - a);
    return                       (d - x) / (d - c);
}

/* ── Compute firing strengths for all 25 rules ──────────────────────────── */
/*
 * pH fuzzy sets (5):
 *   0 VeryAcidic  : a=5.5, b=5.5, c=6.0, d=6.5
 *   1 Acidic      : a=5.5, b=6.0, c=6.5, d=7.0
 *   2 Normal      : a=6.5, b=7.0, c=7.5, d=8.0
 *   3 Alkaline    : a=7.5, b=8.0, c=8.5, d=9.0
 *   4 VeryAlkaline: a=8.5, b=9.0, c=9.5, d=9.5
 *
 * Temperature fuzzy sets (5):
 *   0 VeryCold : a=17.5, b=17.5, c=18.0, d=20.0
 *   1 Cold     : a=18.0, b=20.0, c=22.0, d=25.0
 *   2 Optimal  : a=22.0, b=25.0, c=29.0, d=32.0
 *   3 Hot      : a=29.0, b=32.0, c=33.0, d=34.5
 *   4 VeryHot  : a=33.0, b=34.0, c=35.0, d=35.0
 *
 * Rule index = pH_idx * 5 + T_idx  (row-major, matches Python _RULE_ORDER)
 */
static void calc_firing_strengths(float ph, float temp, float phi[FQL_N_RULES]) {
    /* pH membership (5 sets) */
    float mu_ph[FQL_N_PH_SETS];
    mu_ph[0] = trapezoid(ph, 5.5f, 5.5f, 6.0f, 6.5f);  /* VeryAcidic   */
    mu_ph[1] = trapezoid(ph, 5.5f, 6.0f, 6.5f, 7.0f);  /* Acidic       */
    mu_ph[2] = trapezoid(ph, 6.5f, 7.0f, 7.5f, 8.0f);  /* Normal       */
    mu_ph[3] = trapezoid(ph, 7.5f, 8.0f, 8.5f, 9.0f);  /* Alkaline     */
    mu_ph[4] = trapezoid(ph, 8.5f, 9.0f, 9.5f, 9.5f);  /* VeryAlkaline */

    /* Temperature membership (5 sets) */
    float mu_t[FQL_N_T_SETS];
    mu_t[0] = trapezoid(temp, 17.5f, 17.5f, 18.0f, 20.0f);  /* VeryCold */
    mu_t[1] = trapezoid(temp, 18.0f, 20.0f, 22.0f, 25.0f);  /* Cold     */
    mu_t[2] = trapezoid(temp, 22.0f, 25.0f, 29.0f, 32.0f);  /* Optimal  */
    mu_t[3] = trapezoid(temp, 29.0f, 32.0f, 33.0f, 34.5f);  /* Hot      */
    mu_t[4] = trapezoid(temp, 33.0f, 34.0f, 35.0f, 35.0f);  /* VeryHot  */

    /* phi[i*5 + j] = mu_ph[i] × mu_t[j] */
    for (int i = 0; i < FQL_N_PH_SETS; i++)
        for (int j = 0; j < FQL_N_T_SETS; j++)
            phi[i * FQL_N_T_SETS + j] = mu_ph[i] * mu_t[j];
}

/* ── FQL inference ──────────────────────────────────────────────────────── */
uint8_t fql_select_action(int32_t ph_x1000, int32_t temp_x100,
                           const FQL_QTable_t *qt) {
    float ph   = ph_x1000  / 1000.0f;
    float temp = temp_x100 / 100.0f;

    float phi[FQL_N_RULES];
    calc_firing_strengths(ph, temp, phi);

    /* Q_FQL(a) = Σ_r phi_r × q[r][a] */
    float q_fql[FQL_N_ACTIONS] = {0};
    for (int r = 0; r < FQL_N_RULES; r++) {
        if (phi[r] <= 0.0f) continue;
        for (int a = 0; a < FQL_N_ACTIONS; a++)
            q_fql[a] += phi[r] * qt->q[r][a];
    }

    /* Return action with highest Q_FQL */
    uint8_t best = 0;
    for (int a = 1; a < FQL_N_ACTIONS; a++)
        if (q_fql[a] > q_fql[best]) best = a;

    return best;
}

/* ── Parse Q-table from string ──────────────────────────────────────────── */
/*
 * Format: "QTABLE:[[q00,q01,q02,q03],[q10,...],...]\n"
 * Strategy: skip "QTABLE:" prefix, scan 100 floats sequentially with strtof.
 */
bool fql_parse_qtable(const char *json_str, FQL_QTable_t *qt) {
    const char *p = strstr(json_str, "QTABLE:");
    if (!p) return false;
    p += 7;

    int   count = 0;
    char *end;

    while (*p && count < FQL_N_RULES * FQL_N_ACTIONS) {
        while (*p && *p != '-' && (*p < '0' || *p > '9')) p++;
        if (!*p) break;

        float val = strtof(p, &end);
        if (end == p) { p++; continue; }

        int r = count / FQL_N_ACTIONS;
        int a = count % FQL_N_ACTIONS;
        qt->q[r][a] = val;
        count++;
        p = end;
    }

    if (count != FQL_N_RULES * FQL_N_ACTIONS) return false;

    qt->loaded = true;
    return true;
}

/* ── Check USB input (non-blocking) ─────────────────────────────────────── */
void check_usb_input(FQL_QTable_t *qt) {
    int c;
    while ((c = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
        if (c == '\n' || c == '\r') {
            _usb_buf[_usb_pos] = '\0';

            if (strncmp(_usb_buf, "QTABLE:", 7) == 0) {
                if (fql_parse_qtable(_usb_buf, qt)) {
                    printf("ACK:QTABLE_LOADED\n");
                    printf("# ============================================================\r\n");
                    printf("# *** Q-TABLE RECEIVED — FQL MODE ACTIVE ***\r\n");
                    printf("# %d rules x %d actions loaded from RPi\r\n",
                           FQL_N_RULES, FQL_N_ACTIONS);
                    printf("# Monitor label: [FQL] = FQL inference | [RB ] = Rule-Based\r\n");
                    printf("# ============================================================\r\n");
                } else {
                    printf("ACK:QTABLE_ERROR\n");
                    printf("# [ERROR] Q-table parse failed — staying in Rule-Based mode\r\n");
                }
            }

            _usb_pos = 0;
        } else {
            if (_usb_pos < USB_BUF_SIZE - 1)
                _usb_buf[_usb_pos++] = (char)c;
        }
    }
}
