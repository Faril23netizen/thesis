#ifndef FQL_INFERENCE_H
#define FQL_INFERENCE_H

#include <stdint.h>
#include <stdbool.h>

/*
 * FQL Inference — Raspberry Pi Pico WH (RP2040)
 * ================================================
 * Menerima Q-table dari RPi 4 via USB Serial,
 * lalu melakukan FQL inference lokal di Pico.
 *
 * 9 rules × 4 aksi = 36 nilai float (144 bytes)
 * State: (pH, Temperature)
 * Aksi : 0=OFF, 1=LOW, 2=MED, 3=HIGH
 */

/* ── Konstanta aksi ─────────────────────────────────────────────────────── */
#define FQL_ACTION_OFF   0
#define FQL_ACTION_LOW   1
#define FQL_ACTION_MED   2
#define FQL_ACTION_HIGH  3
#define FQL_N_RULES      9
#define FQL_N_ACTIONS    4

/* ── Q-table struct ─────────────────────────────────────────────────────── */
typedef struct {
    float q[FQL_N_RULES][FQL_N_ACTIONS];  /* 9×4 = 36 nilai float */
    bool  loaded;                          /* true setelah Q-table diterima */
} FQL_QTable_t;

/*
 * Parse Q-table dari string JSON yang dikirim RPi 4.
 * Format: "QTABLE:[[q00,q01,q02,q03],[q10,...],...]"
 * Return: true jika berhasil parse 36 nilai, false jika format salah.
 */
bool fql_parse_qtable(const char *json_str, FQL_QTable_t *qt);

/*
 * Cek input USB setiap loop (non-blocking).
 * Baca baris dari stdin → kalau diawali "QTABLE:" → parse dan simpan.
 * Cetak "ACK:QTABLE_LOADED\n" setelah berhasil.
 */
void check_usb_input(FQL_QTable_t *qt);

/*
 * FQL inference: hitung firing strength 9 rules, lalu pilih aksi
 * dengan Q_FQL tertinggi.
 * ph  = pH × 1000 (integer), temp = T × 100 (integer)
 */
uint8_t fql_select_action(int32_t ph_x1000, int32_t temp_x100,
                           const FQL_QTable_t *qt);

#endif /* FQL_INFERENCE_H */
