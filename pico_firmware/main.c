/*
 * Risk Monitoring Node — Raspberry Pi Pico WH (RP2040)
 * =====================================================
 * Thesis : Edge-Intelligent Aquaculture NH3 Risk Monitoring
 * Student: Faril Pirwanhadi (M14128104)
 *
 * Hardware:
 *   pH Sensor Module → ADC0 (GPIO26)
 *   DS18B20          → GPIO15, pull-up 4.7 kΩ ke 3.3 V
 *   Output           → Wi-Fi TCP Socket (N3IWF LES)
 */

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "hardware/adc.h"
#include "hardware/gpio.h"

#include "lwip/pbuf.h"
#include "lwip/tcp.h"

#include "ds18b20.h"
#include "ph_sensor.h"

/* ── Configuration ───────────────────────────────────────────────────────── */
#define WIFI_SSID "N3IWF_AQUA"
#define WIFI_PASSWORD "skripsi2026"
#define N3IWF_SERVER_IP "10.42.0.1"
#define N3IWF_PORT 5000

#define TEMP_GPIO_PIN 15
#define SAMPLE_INTERVAL_MS 2000

/* ── Risk levels ─────────────────────────────────────────────────────────── */
#define RISK_SAFE 0
#define RISK_CAUTION 1
#define RISK_WARNING 2
#define RISK_CRITICAL 3

/* ── Global sensor instances ─────────────────────────────────────────────── */
static DS18B20_t g_ds18b20;

/* ── TCP Client State ────────────────────────────────────────────────────── */
typedef struct {
    struct tcp_pcb *tcp_pcb;
    ip_addr_t remote_addr;
    bool connected;
} tcp_client_t;

static tcp_client_t *g_client = NULL;

/* ── NH3 calculation ─────────────────────────────────────────────────────── */
static int32_t calc_nh3_x100000(int32_t ph_x1000, int32_t temp_x100) {
  float ph = ph_x1000 / 1000.0f;
  float temp = temp_x100 / 100.0f;
  float pka = 0.09018f + 2729.92f / (temp + 273.15f);
  float fnh3 = 1.0f / (1.0f + powf(10.0f, pka - ph));
  return (int32_t)(fnh3 * 100000.0f);
}

static uint8_t calc_risk_level(int32_t nh3_x100000) {
  float nh3_pct = nh3_x100000 / 1000.0f;
  if (nh3_pct < 1.0f) return RISK_SAFE;
  else if (nh3_pct < 5.0f) return RISK_CAUTION;
  else if (nh3_pct < 10.0f) return RISK_WARNING;
  else return RISK_CRITICAL;
}

static const char *risk_str(uint8_t r) {
  switch (r) {
  case RISK_SAFE: return "SAFE";
  case RISK_CAUTION: return "CAUTION";
  case RISK_WARNING: return "WARNING";
  case RISK_CRITICAL: return "CRITICAL";
  default: return "?";
  }
}

/* ── TCP callbacks ───────────────────────────────────────────────────────── */
static err_t tcp_client_close(tcp_client_t *state) {
    err_t err = ERR_OK;
    if (state->tcp_pcb) {
        tcp_arg(state->tcp_pcb, NULL);
        tcp_poll(state->tcp_pcb, NULL, 0);
        tcp_sent(state->tcp_pcb, NULL);
        tcp_recv(state->tcp_pcb, NULL);
        tcp_err(state->tcp_pcb, NULL);
        err = tcp_close(state->tcp_pcb);
        if (err != ERR_OK) {
            printf("# TCP close failed, aborting\n");
            tcp_abort(state->tcp_pcb);
            err = ERR_ABRT;
        }
        state->tcp_pcb = NULL;
    }
    state->connected = false;
    return err;
}

static void tcp_client_err(void *arg, err_t err) {
    tcp_client_t *state = (tcp_client_t*)arg;
    printf("# TCP error %d\n", err);
    if (err != ERR_ABRT) {
        tcp_client_close(state);
    }
}

static err_t tcp_client_connected(void *arg, struct tcp_pcb *tpcb, err_t err) {
    tcp_client_t *state = (tcp_client_t*)arg;
    if (err != ERR_OK) {
        printf("# Connect failed %d\n", err);
        return tcp_client_close(state);
    }
    state->connected = true;
    printf("# TCP connected!\n");
    return ERR_OK;
}

static bool tcp_client_open(tcp_client_t *state) {
    printf("# Connecting to %s:%d\n", ip4addr_ntoa(&state->remote_addr), N3IWF_PORT);
    
    state->tcp_pcb = tcp_new_ip_type(IP_GET_TYPE(&state->remote_addr));
    if (!state->tcp_pcb) {
        printf("# Failed to create PCB\n");
        return false;
    }

    tcp_arg(state->tcp_pcb, state);
    tcp_err(state->tcp_pcb, tcp_client_err);

    cyw43_arch_lwip_begin();
    err_t err = tcp_connect(state->tcp_pcb, &state->remote_addr, N3IWF_PORT, tcp_client_connected);
    cyw43_arch_lwip_end();

    return err == ERR_OK;
}

static tcp_client_t* tcp_client_init(void) {
    tcp_client_t *state = calloc(1, sizeof(tcp_client_t));
    if (!state) {
        printf("# Failed to allocate state\n");
        return NULL;
    }
    ip4addr_aton(N3IWF_SERVER_IP, &state->remote_addr);
    return state;
}

/* ── Send data ───────────────────────────────────────────────────────────── */
static bool tcp_client_send_data(tcp_client_t *state, int32_t ph_x1000, int32_t temp_x100, uint8_t risk) {
    if (!state || !state->connected || !state->tcp_pcb) {
        return false;
    }

    char buf[64];
    snprintf(buf, sizeof(buf), "DATA:%ld,%ld,%u\n", 
             (long)ph_x1000, (long)temp_x100, (unsigned)risk);

    cyw43_arch_lwip_begin();
    err_t err = tcp_write(state->tcp_pcb, buf, strlen(buf), TCP_WRITE_FLAG_COPY);
    if (err == ERR_OK) {
        err = tcp_output(state->tcp_pcb);
    }
    cyw43_arch_lwip_end();

    if (err != ERR_OK) {
        printf("# TCP send failed: %d\n", err);
        return false;
    }

    return true;
}

/* ══════════════════════════════════════════════════════════════════════════ */
/*                              MAIN                                          */
/* ══════════════════════════════════════════════════════════════════════════ */
int main(void) {
  stdio_init_all();
  sleep_ms(2000);

  printf("\r\n");
  printf("============================================================\r\n");
  printf("  Risk Monitoring Node — Pico WH\r\n");
  printf("  N3IWF Edge Service\r\n");
  printf("============================================================\r\n");
  printf("  SSID: %s\r\n", WIFI_SSID);
  printf("  Server: %s:%d\r\n", N3IWF_SERVER_IP, N3IWF_PORT);
  printf("  Protocol: DATA:ph_x1000,temp_x100,risk\r\n");
  printf("============================================================\r\n");
  printf("\r\n");

  /* ── Initialize CYW43 (Wi-Fi chip) ────────────────────────────────────── */
  if (cyw43_arch_init()) {
    printf("# [FATAL] cyw43_arch_init() failed\r\n");
    return 1;
  }
  cyw43_arch_enable_sta_mode();

  /* ── Initialize sensors ───────────────────────────────────────────────── */
  ph_sensor_init();
  if (!ds18b20_init(&g_ds18b20, TEMP_GPIO_PIN)) {
    printf("# [WARN] DS18B20 not detected on GPIO%d\r\n", TEMP_GPIO_PIN);
  }

  printf("# Sensors initialized.\r\n");
  printf("# \r\n");

  /* ── Connect Wi-Fi ────────────────────────────────────────────────────── */
  printf("# Connecting to Wi-Fi: %s ...\r\n", WIFI_SSID);
  while (cyw43_arch_wifi_connect_timeout_ms(WIFI_SSID, WIFI_PASSWORD,
                                            CYW43_AUTH_WPA2_AES_PSK,
                                            30000) != 0) {
    printf("# Wi-Fi connection failed, retrying in 5s...\r\n");
    sleep_ms(5000);
  }
  printf("# Wi-Fi connected! IP: %s\r\n",
         ip4addr_ntoa(netif_ip4_addr(netif_default)));

  /* ── Initialize TCP client ────────────────────────────────────────────── */
  g_client = tcp_client_init();
  if (!g_client) {
    printf("# [FATAL] Failed to init TCP client\r\n");
    return 1;
  }

  /* ── Connect to N3IWF TCP Server ──────────────────────────────────────── */
  while (!tcp_client_open(g_client)) {
    printf("# TCP connect failed, retrying in 5s...\r\n");
    sleep_ms(5000);
  }

  /* Wait for connection to establish */
  int timeout = 50; /* 5 seconds */
  while (!g_client->connected && timeout > 0) {
    sleep_ms(100);
    timeout--;
  }

  if (!g_client->connected) {
    printf("# [ERROR] TCP connection timeout\r\n");
    return 1;
  }

  printf("# \r\n");
  printf("# Starting data stream...\r\n");
  printf("# \r\n");
  printf(">  Num |   Time  |   pH   | Temp°C |  NH3%%  | Risk\r\n");
  printf("> -----|---------|--------|--------|--------|---------------\r\n");

  uint32_t sample_num = 0;
  uint32_t last_sample_ms = 0;

  /* ══════════════════════════════════════════════════════════════════════ */
  /*                          MAIN LOOP                                     */
  /* ══════════════════════════════════════════════════════════════════════ */
  while (true) {
    uint32_t now_ms = to_ms_since_boot(get_absolute_time());

    /* ── Sample every SAMPLE_INTERVAL_MS ────────────────────────────────── */
    if (now_ms - last_sample_ms >= SAMPLE_INTERVAL_MS) {
      last_sample_ms = now_ms;
      sample_num++;

      /* ── 1. Trigger DS18B20 conversion (750 ms for 12-bit) ────────────── */
      ds18b20_convert(&g_ds18b20);

      /* ── 2. Read pH sensor (parallel with DS18B20 conversion) ──────────── */
      int32_t ph_x1000 = ph_read(&PH_CAL_DEFAULT);

      /* ── 3. Wait for DS18B20 conversion to complete ────────────────────── */
      sleep_ms(800);

      /* ── 4. Read temperature ───────────────────────────────────────────── */
      int32_t temp_x100 = ds18b20_read_raw(&g_ds18b20);

      /* ── 5. Calculate NH3 and risk level ───────────────────────────────── */
      int32_t nh3_x100000 = calc_nh3_x100000(ph_x1000, temp_x100);
      uint8_t risk = calc_risk_level(nh3_x100000);

      /* ── 6. Send data to RPi5 via Wi-Fi TCP ────────────────────────────── */
      if (!tcp_client_send_data(g_client, ph_x1000, temp_x100, risk)) {
        printf("# [WARN] TCP send failed — reconnecting...\r\n");
        tcp_client_close(g_client);
        while (!tcp_client_open(g_client)) {
          printf("# Retry TCP in 3s...\r\n");
          sleep_ms(3000);
        }
        /* Wait for connection */
        timeout = 50;
        while (!g_client->connected && timeout > 0) {
          sleep_ms(100);
          timeout--;
        }
      }

      /* ── 7. Print to serial monitor ────────────────────────────────────── */
      const char *bars[] = {"[----]", "[#---]", "[##--]", "[####]"};
      printf("> %4lu | %7.1fs | %6.3f | %5.2f | %6.3f%% | %s %s\r\n",
             (unsigned long)sample_num, now_ms / 1000.0f, ph_x1000 / 1000.0f,
             temp_x100 / 100.0f, nh3_x100000 / 1000.0f, bars[risk],
             risk_str(risk));
    }

    /* ── Blink LED to show alive ──────────────────────────────────────────── */
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, (now_ms / 500) % 2);

    /* ── Small delay to prevent busy-wait ─────────────────────────────────── */
    sleep_ms(10);
  }

  /* Cleanup (never reached) */
  tcp_client_close(g_client);
  free(g_client);
  cyw43_arch_deinit();
  return 0;
}
