/*
 * Data Collection Capacity Test — Raspberry Pi Pico (RP2040)
 * ============================================================
 * Thesis : Edge-Intelligent Aquaculture Aerator Control
 *          Using Progressive Hybrid FQL-DQN with N3IWF LES
 * Student: Faril Pirwanhadi (M14128104)
 * Advisor: Yi-Chih Tung, En-Cheng Liou
 *
 * Tujuan:
 *   Mengukur berapa banyak record (pH, Temp, NH3, timestamp) yang bisa
 *   ditampung di SRAM RP2040 (264 KB), dan menguji throughput sensor.
 *
 * Hardware:
 *   pH Sensor Module → ADC0 (GPIO26)
 *   DS18B20          → GPIO15, pull-up 4.7 kΩ ke 3.3 V
 *   Output           → USB Serial (115200 baud)
 *
 * Build:
 *   mkdir build && cd build
 *   cmake .. && make -j4
 *   Flash UF2 ke Pico via BOOTSEL
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "pico/time.h"

#include "ph_sensor.h"
#include "ds18b20.h"
#include "pico/cyw43_arch.h"

/* ── Konfigurasi test ───────────────────────────────────────────────────── */
#define TEMP_GPIO_PIN       15      /* DS18B20 data pin */
#define SAMPLE_INTERVAL_MS  1000    /* interval antar sample (ms)           */
#define RECORDS_INIT_CAP    64      /* kapasitas awal buffer (akan grow otomatis) */

/* ── Struktur satu record data ──────────────────────────────────────────── */
typedef struct {
    uint32_t timestamp_ms;  /* 4 bytes */
    int32_t  ph_x1000;      /* 4 bytes — pH × 1000, e.g. 7015 = 7.015     */
    int32_t  temp_x100;     /* 4 bytes — °C × 100,  e.g. 2501 = 25.01°C   */
    int32_t  nh3_x100000;   /* 4 bytes — NH3 frac × 100000 (0–100000)     */
    uint16_t adc_raw;       /* 2 bytes — raw ADC value untuk debug         */
    uint8_t  status;        /* 1 byte  — 0=SAFE, 1=WARNING, 2=DANGER_PH,
                                          3=DANGER_TEMP                    */
    uint8_t  _pad;          /* 1 byte padding → total = 20 bytes/record    */
} SensorRecord_t;           /* sizeof = 20 bytes */

/* Dynamic buffer — grows sampai RAM habis */
static SensorRecord_t *records      = NULL;
static uint32_t        records_cap  = 0;

/* ── NH3 chemistry (Eq. 2.1 & 2.2 dari laporan) ────────────────────────── */
/*
 * pKa(T) = 0.09018 + 2729.92 / (T + 273.15)
 * f(NH3) = 1 / (1 + 10^(pKa - pH))
 *
 * Gunakan integer-friendly approx: semua × 100000
 * 10^x diimplementasikan lewat lookup table atau exp(x × ln10).
 * Untuk embedded: kita pakai fixed-point pendekatan dengan float hanya di
 * kalkulasi NH3 (dipanggil jarang, bukan hot path inference).
 */
#include <math.h>
#include <stdlib.h>

static int32_t calc_nh3_x100000(int32_t ph_x1000, int32_t temp_x100) {
    float ph   = ph_x1000  / 1000.0f;
    float temp = temp_x100 / 100.0f;
    float pka  = 0.09018f + 2729.92f / (temp + 273.15f);
    float fnh3 = 1.0f / (1.0f + powf(10.0f, pka - ph));
    return (int32_t)(fnh3 * 100000.0f);
}

/* ── Stage 1 Rule-Based Safety Check ───────────────────────────────────── */
/*
 * Status codes:
 *   0 = SAFE       (6.5 ≤ pH ≤ 8.5, T ≤ 30°C)
 *   1 = WARNING    (6.0 ≤ pH < 6.5 atau 8.5 < pH ≤ 9.5, atau 30 < T ≤ 35)
 *   2 = DANGER_PH  (pH < 6.0 atau pH > 9.5) → aeration HIGH
 *   3 = DANGER_TEMP(T > 35°C)               → aeration HIGH
 */
static uint8_t safety_check(int32_t ph_x1000, int32_t temp_x100) {
    int32_t ph_lo  = ph_x1000;
    int32_t temp_c = temp_x100;

    if (ph_lo < 6000 || ph_lo > 9500) return 2;   /* DANGER_PH  */
    if (temp_c > 3500)                return 3;   /* DANGER_TEMP */
    if (ph_lo >= 6500 && ph_lo <= 8500 && temp_c <= 3000) return 0; /* SAFE */
    return 1;                                      /* WARNING    */
}

static const char *status_str(uint8_t s) {
    switch (s) {
        case 0: return "SAFE       ";
        case 1: return "WARNING    ";
        case 2: return "DANGER_PH  ";
        case 3: return "DANGER_TEMP";
        default:return "UNKNOWN    ";
    }
}

/* ── Estimasi free SRAM (heap guard trick) ──────────────────────────────── */
static uint32_t estimate_free_ram(void) {
    /* Malloc probe: cari blok terbesar yang masih bisa dialokasikan */
    uint32_t size = 100 * 1024;   /* mulai dari 100 KB */
    void *p = NULL;
    while (size >= 256 && p == NULL) {
        p = malloc(size);
        if (!p) size -= 256;
    }
    if (p) free(p);
    return size;
}

/* ── Print header tabel ─────────────────────────────────────────────────── */
static void print_header(void) {
    printf("\r\n");
    printf("================================================================\r\n");
    printf("  DATA COLLECTION CAPACITY TEST — RP2040 Pico\r\n");
    printf("  Thesis: Progressive Hybrid FQL-DQN Aquaculture\r\n");
    printf("  Faril Pirwanhadi | M14128104\r\n");
    printf("================================================================\r\n");
    printf("  sizeof(SensorRecord_t) = %u bytes\r\n", (unsigned)sizeof(SensorRecord_t));
    printf("  Buffer                 = dinamis (grow sampai RAM habis)\r\n");
    printf("  Sample interval        = %d ms\r\n", SAMPLE_INTERVAL_MS);
    printf("  Stop condition         = free RAM < 10 KB\r\n");
    printf("================================================================\r\n");
    printf("\r\n");
    printf("  #    | Time(s) |   pH   | Temp°C | NH3%%    | ADC  | FreeRAM | Status\r\n");
    printf("-------|---------|--------|--------|---------|------|---------|------------\r\n");
}

/* ── Print ringkasan akhir ──────────────────────────────────────────────── */
static void print_summary(uint32_t count, uint32_t total_ms) {
    printf("\r\n================================================================\r\n");
    printf("  RINGKASAN TEST\r\n");
    printf("================================================================\r\n");
    printf("  Total records      : %lu\r\n", (unsigned long)count);
    printf("  Durasi total       : %lu ms (%.1f s)\r\n",
           (unsigned long)total_ms, total_ms / 1000.0f);
    printf("  Avg interval       : %lu ms/record\r\n",
           count > 0 ? (unsigned long)(total_ms / count) : 0);
    printf("  Buffer used        : %lu bytes (%.1f KB)\r\n",
           (unsigned long)(count * sizeof(SensorRecord_t)),
           count * sizeof(SensorRecord_t) / 1024.0f);

    if (count > 0) {
        /* Statistik pH & Temp */
        int32_t ph_min  = records[0].ph_x1000,  ph_max  = records[0].ph_x1000;
        int32_t t_min   = records[0].temp_x100, t_max   = records[0].temp_x100;
        int64_t ph_sum  = 0, t_sum = 0;

        uint32_t status_cnt[4] = {0};

        for (uint32_t i = 0; i < count; i++) {
            if (records[i].ph_x1000  < ph_min) ph_min = records[i].ph_x1000;
            if (records[i].ph_x1000  > ph_max) ph_max = records[i].ph_x1000;
            if (records[i].temp_x100 < t_min)  t_min  = records[i].temp_x100;
            if (records[i].temp_x100 > t_max)  t_max  = records[i].temp_x100;
            ph_sum += records[i].ph_x1000;
            t_sum  += records[i].temp_x100;
            if (records[i].status < 4) status_cnt[records[i].status]++;
        }

        int32_t ph_avg = (int32_t)(ph_sum / count);
        int32_t t_avg  = (int32_t)(t_sum  / count);

        printf("\r\n  pH  → min=%ld.%03ld  max=%ld.%03ld  avg=%ld.%03ld\r\n",
               (long)(ph_min/1000), (long)((ph_min < 0 ? -ph_min : ph_min)%1000),
               (long)(ph_max/1000), (long)(ph_max%1000),
               (long)(ph_avg/1000), (long)((ph_avg < 0 ? -ph_avg : ph_avg)%1000));
        printf("  T°C → min=%ld.%02ld  max=%ld.%02ld  avg=%ld.%02ld\r\n",
               (long)(t_min/100), (long)((t_min < 0 ? -t_min : t_min)%100),
               (long)(t_max/100), (long)(t_max%100),
               (long)(t_avg/100), (long)((t_avg < 0 ? -t_avg : t_avg)%100));

        printf("\r\n  Status distribution:\r\n");
        const char *snames[] = {"SAFE", "WARNING", "DANGER_PH", "DANGER_TEMP"};
        for (int s = 0; s < 4; s++) {
            if (status_cnt[s] > 0)
                printf("    %-12s: %lu records (%lu%%)\r\n",
                       snames[s], (unsigned long)status_cnt[s],
                       (unsigned long)(status_cnt[s] * 100 / count));
        }

        /* Estimasi kapasitas max berdasarkan ukuran record */
        uint32_t sram_total = 264 * 1024;
        uint32_t rec_size   = sizeof(SensorRecord_t);
        uint32_t est_max_50 = (sram_total / 2) / rec_size;
        uint32_t est_max_70 = (sram_total * 7 / 10) / rec_size;
        printf("\r\n  Estimasi kapasitas SRAM 264 KB:\r\n");
        printf("    50%% SRAM (132 KB) → ~%lu records\r\n", (unsigned long)est_max_50);
        printf("    70%% SRAM (185 KB) → ~%lu records\r\n", (unsigned long)est_max_70);
        printf("    (sisanya untuk code, stack, TFLM runtime, FQL Q-table 144B)\r\n");
    }

    printf("================================================================\r\n");
    printf("  [DONE] Test selesai.\r\n");
    printf("================================================================\r\n");
}

/* ── Dump semua record sebagai CSV ──────────────────────────────────────── */
static void dump_csv(uint32_t count) {
    printf("\r\n");
    printf("==== CSV DUMP START ====\r\n");
    printf("index,timestamp_ms,ph,temp_c,nh3_pct,adc_raw,status\r\n");
    for (uint32_t i = 0; i < count; i++) {
        SensorRecord_t *r = &records[i];
        printf("%lu,%lu,%ld.%03ld,%ld.%02ld,%ld.%03ld,%u,%u\r\n",
               (unsigned long)i + 1,
               (unsigned long)r->timestamp_ms,
               (long)(r->ph_x1000 / 1000),
               (long)((r->ph_x1000 < 0 ? -r->ph_x1000 : r->ph_x1000) % 1000),
               (long)(r->temp_x100 / 100),
               (long)((r->temp_x100 < 0 ? -r->temp_x100 : r->temp_x100) % 100),
               (long)(r->nh3_x100000 / 1000),
               (long)(r->nh3_x100000 % 1000),
               (unsigned)r->adc_raw,
               (unsigned)r->status);
    }
    printf("==== CSV DUMP END ====\r\n");
}

/* ── main ───────────────────────────────────────────────────────────────── */
int main(void) {
    /* Init stdio USB */
    stdio_init_all();

    /* Init CYW43 (Pico W/WH) — harus dipanggil sebelum apa pun */
    cyw43_arch_init();

    /* Tunggu sampai terminal USB benar-benar terhubung */
    while (!stdio_usb_connected()) sleep_ms(100);

    /* Init sensor */
    ph_sensor_init();

    DS18B20_t ds_dev;
    bool ds_ok = ds18b20_init(&ds_dev, TEMP_GPIO_PIN);
    if (!ds_ok) {
        printf("[ERROR] DS18B20 tidak terdeteksi pada GPIO%d!\r\n", TEMP_GPIO_PIN);
        printf("        Cek wiring: data → GPIO15, pull-up 4.7kΩ ke 3.3V\r\n");
        while (true) tight_loop_contents();
    }

    printf("[OK] DS18B20 ROM: %02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X\r\n",
           ds_dev.rom[0], ds_dev.rom[1], ds_dev.rom[2], ds_dev.rom[3],
           ds_dev.rom[4], ds_dev.rom[5], ds_dev.rom[6], ds_dev.rom[7]);

    print_header();

    /* Alokasi buffer awal */
    records     = malloc(RECORDS_INIT_CAP * sizeof(SensorRecord_t));
    records_cap = RECORDS_INIT_CAP;
    if (!records) {
        printf("[ERROR] malloc awal gagal!\r\n");
        while (true) tight_loop_contents();
    }

    uint32_t start_ms    = to_ms_since_boot(get_absolute_time());
    uint32_t record_count = 0;

    while (true) {
        uint32_t loop_start = to_ms_since_boot(get_absolute_time());
        uint32_t elapsed_ms = loop_start - start_ms;

        /* ── Baca sensor ─────────────────────────────────────────────── */
        /* DS18B20: trigger konversi dulu (750 ms), baca setelah itu */
        ds18b20_convert(&ds_dev);

        /* Sambil nunggu DS18B20, baca pH (cepat ~5 ms) */
        uint16_t adc_raw   = ph_sensor_read_raw();
        int32_t  ph_mv     = ph_adc_to_mv(adc_raw);
        int32_t  ph_x1000  = ph_mv_to_ph(ph_mv, &PH_CAL_DEFAULT);

        /* Tunggu sisa waktu konversi DS18B20 (750 ms total) */
        uint32_t elapsed_read = to_ms_since_boot(get_absolute_time()) - loop_start;
        if (elapsed_read < 760) sleep_ms(760 - elapsed_read);

        int32_t temp_x100 = ds18b20_read_raw(&ds_dev);
        if (temp_x100 == INT32_MIN) {
            printf("[WARN] CRC error DS18B20 pada record #%lu, skip.\r\n",
                   (unsigned long)record_count);
            continue;
        }

        int32_t nh3_x100000 = calc_nh3_x100000(ph_x1000, temp_x100);
        uint8_t status      = safety_check(ph_x1000, temp_x100);

        /* ── Grow buffer jika penuh ─────────────────────────────────── */
        if (record_count >= records_cap) {
            uint32_t new_cap = records_cap * 2;
            SensorRecord_t *tmp = realloc(records, new_cap * sizeof(SensorRecord_t));
            if (!tmp) {
                printf("\r\n[WARN] realloc gagal, buffer penuh di %lu records.\r\n",
                       (unsigned long)record_count);
                break;
            }
            records     = tmp;
            records_cap = new_cap;
        }

        /* ── Simpan ke buffer ────────────────────────────────────────── */
        records[record_count].timestamp_ms = elapsed_ms;
        records[record_count].ph_x1000     = ph_x1000;
        records[record_count].temp_x100    = temp_x100;
        records[record_count].nh3_x100000  = nh3_x100000;
        records[record_count].adc_raw      = adc_raw;
        records[record_count].status       = status;
        records[record_count]._pad         = 0;
        record_count++;

        /* ── Estimasi free RAM ───────────────────────────────────────── */
        uint32_t free_ram = estimate_free_ram();

        /* ── Cetak baris ─────────────────────────────────────────────── */
        printf("%5lu | %7.1f | %ld.%03ld | %ld.%02ld | %ld.%03ld%% | %4u | %5luK  | %s\r\n",
               (unsigned long)record_count,
               elapsed_ms / 1000.0f,
               (long)(ph_x1000 / 1000),
               (long)((ph_x1000 < 0 ? -ph_x1000 : ph_x1000) % 1000),
               (long)(temp_x100 / 100),
               (long)((temp_x100 < 0 ? -temp_x100 : temp_x100) % 100),
               (long)(nh3_x100000 / 1000),
               (long)(nh3_x100000 % 1000),
               (unsigned)adc_raw,
               (unsigned long)(free_ram / 1024),
               status_str(status));

        /* ── Warning memory rendah ───────────────────────────────────── */
        if (free_ram < 10 * 1024) {
            printf("\r\n[WARN] Free RAM < 10 KB (%lu bytes). Berhenti.\r\n",
                   (unsigned long)free_ram);
            break;
        }

        /* ── Tunggu interval berikutnya ──────────────────────────────── */
        uint32_t loop_dur = to_ms_since_boot(get_absolute_time()) - loop_start;
        if (loop_dur < SAMPLE_INTERVAL_MS) {
            sleep_ms(SAMPLE_INTERVAL_MS - loop_dur);
        }
    }

    uint32_t total_ms = to_ms_since_boot(get_absolute_time()) - start_ms;
    print_summary(record_count, total_ms);
    dump_csv(record_count);

    /* Blink LED onboard selamanya sebagai tanda selesai (Pico W/WH) */
    while (true) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1); sleep_ms(200);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0); sleep_ms(200);
    }
}
