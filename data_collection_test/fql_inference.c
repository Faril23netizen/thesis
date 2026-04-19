/*
 * FQL Inference — Implementasi
 * ==============================
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

/* ── Buffer baca serial ─────────────────────────────────────────────────── */
#define USB_BUF_SIZE  512
static char  _usb_buf[USB_BUF_SIZE];
static int   _usb_pos = 0;

/* ── Trapezoidal membership function ────────────────────────────────────── */
/*
 * mu(x, a, b, c, d):
 *   0           jika x <= a atau x >= d
 *   (x-a)/(b-a) jika a < x < b
 *   1.0         jika b <= x <= c
 *   (d-x)/(d-c) jika c < x < d
 */
static float trapezoid(float x, float a, float b, float c, float d) {
    if (x <= a || x >= d) return 0.0f;
    if (x >= b && x <= c) return 1.0f;
    if (x < b)            return (x - a) / (b - a);
    return                       (d - x) / (d - c);
}

/* ── Hitung firing strength semua 9 rules ───────────────────────────────── */
/*
 * pH sets (3):
 *   Acidic  : a=5.5, b=5.5, c=6.5, d=7.0
 *   Normal  : a=6.5, b=7.0, c=7.5, d=8.0  (typo di spec diperbaiki: b=7.0)
 *   Alkaline: a=7.5, b=8.0, c=9.5, d=9.5
 *
 * Temp sets (3):
 *   Cold   : a=17.5, b=17.5, c=20.0, d=25.0
 *   Optimal: a=22.0, b=25.0, c=30.0, d=33.0
 *   Hot    : a=30.0, b=33.0, c=35.0, d=35.0
 *
 * 9 rules = pH set × Temp set (outer product, row-major):
 *   Rule 0: Acidic   × Cold     Rule 3: Normal   × Cold
 *   Rule 1: Acidic   × Optimal  Rule 4: Normal   × Optimal
 *   Rule 2: Acidic   × Hot      Rule 5: Normal   × Hot
 *                               Rule 6: Alkaline × Cold
 *                               Rule 7: Alkaline × Optimal
 *                               Rule 8: Alkaline × Hot
 */
static void calc_firing_strengths(float ph, float temp, float phi[FQL_N_RULES]) {
    /* pH membership */
    float mu_ph[3];
    mu_ph[0] = trapezoid(ph, 5.5f, 5.5f, 6.5f, 7.0f);   /* Acidic   */
    mu_ph[1] = trapezoid(ph, 6.5f, 7.0f, 7.5f, 8.0f);   /* Normal   */
    mu_ph[2] = trapezoid(ph, 7.5f, 8.0f, 9.5f, 9.5f);   /* Alkaline */

    /* Temp membership */
    float mu_t[3];
    mu_t[0] = trapezoid(temp, 17.5f, 17.5f, 20.0f, 25.0f);  /* Cold    */
    mu_t[1] = trapezoid(temp, 22.0f, 25.0f, 30.0f, 33.0f);  /* Optimal */
    mu_t[2] = trapezoid(temp, 30.0f, 33.0f, 35.0f, 35.0f);  /* Hot     */

    /* phi_r = mu_pH[i] × mu_T[j], r = i*3 + j */
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            phi[i * 3 + j] = mu_ph[i] * mu_t[j];
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

    /* Pilih aksi dengan Q_FQL tertinggi */
    uint8_t best = 0;
    for (int a = 1; a < FQL_N_ACTIONS; a++)
        if (q_fql[a] > q_fql[best]) best = a;

    return best;
}

/* ── Parse Q-table dari string JSON ─────────────────────────────────────── */
/*
 * Format: "QTABLE:[[q00,q01,q02,q03],[q10,q11,q12,q13],...]\n"
 * Strategi: lewati prefix "QTABLE:", lalu scan angka float satu per satu.
 * Tidak pakai library JSON — cukup strtof + iterasi karakter.
 */
bool fql_parse_qtable(const char *json_str, FQL_QTable_t *qt) {
    /* Lewati prefix "QTABLE:" */
    const char *p = strstr(json_str, "QTABLE:");
    if (!p) return false;
    p += 7;   /* loncat 7 karakter "QTABLE:" */

    int  count = 0;
    char *end;

    while (*p && count < FQL_N_RULES * FQL_N_ACTIONS) {
        /* Cari karakter digit atau '-' (awal angka) */
        while (*p && *p != '-' && (*p < '0' || *p > '9')) p++;
        if (!*p) break;

        float val = strtof(p, &end);
        if (end == p) { p++; continue; }   /* tidak ada angka valid, lewati */

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

/* ── Cek input USB (non-blocking) ───────────────────────────────────────── */
void check_usb_input(FQL_QTable_t *qt) {
    /* Baca karakter yang tersedia tanpa blocking */
    int c;
    while ((c = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
        if (c == '\n' || c == '\r') {
            /* Baris lengkap — proses jika diawali "QTABLE:" */
            _usb_buf[_usb_pos] = '\0';

            if (strncmp(_usb_buf, "QTABLE:", 7) == 0) {
                if (fql_parse_qtable(_usb_buf, qt)) {
                    printf("ACK:QTABLE_LOADED\n");
                    printf("# ============================================================\r\n");
                    printf("# *** Q-TABLE RECEIVED — FQL MODE ACTIVE ***\r\n");
                    printf("# 9 rules x 4 actions loaded from RPi4\r\n");
                    printf("# Monitor label: [FQL] = FQL inference | [RB ] = Rule-Based\r\n");
                    printf("# ============================================================\r\n");
                } else {
                    printf("ACK:QTABLE_ERROR\n");
                    printf("# [ERROR] Q-table parse failed — staying in Rule-Based mode\r\n");
                }
            }

            /* Reset buffer */
            _usb_pos = 0;
        } else {
            /* Simpan karakter, jaga supaya tidak overflow */
            if (_usb_pos < USB_BUF_SIZE - 1)
                _usb_buf[_usb_pos++] = (char)c;
        }
    }
}
