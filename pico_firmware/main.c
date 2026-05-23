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

#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "lwip/dns.h"
#include "lwip/pbuf.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"
#include "pico/cyw43_arch.h"
#include "pico/stdlib.h"
#include "pico/time.h"
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ds18b20.h"
#include "ph_sensor.h"

/* ── Wi-Fi & N3IWF Configuration ──────────────────────────────────────── */
#define WIFI_SSID "N3IWF_AQUA"
#define WIFI_PASSWORD "skripsi2026"
#define N3IWF_SERVER_IP "10.42.0.1"
#define N3IWF_PORT 5000

/* Timeout koneksi Wi-Fi dan socket (ms) */
#define WIFI_CONNECT_TIMEOUT_MS 30000
#define SOCKET_RECV_TIMEOUT_MS 100

/* ── Pin & timing config ──────────────────────────────────────────────── */
#define TEMP_GPIO_PIN 15
#define SAMPLE_INTERVAL_MS 2000

/* ── Risk levels ──────────────────────────────────────────────────────── */
#define RISK_SAFE 0
#define RISK_CAUTION 1
#define RISK_WARNING 2
#define RISK_CRITICAL 3

/* ── NH3 chemistry (Eq. 2.1 & 2.2) ────────────────────────────────────── */
static int32_t calc_nh3_x100000(int32_t ph_x1000, int32_t temp_x100) {
  float ph = ph_x1000 / 1000.0f;
  float temp = temp_x100 / 100.0f;
  float pka = 0.09018f + 2729.92f / (temp + 273.15f);
  float fnh3 = 1.0f / (1.0f + powf(10.0f, pka - ph));
  return (int32_t)(fnh3 * 100000.0f);
}

/* ── Risk level calculation ───────────────────────────────────────────── */
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

/* ── Serial monitor display ───────────────────────────────────────────── */
static void print_monitor(uint32_t num, uint32_t ts_ms, int32_t ph_x1000,
                          int32_t temp_x100, int32_t nh3_x100000,
                          uint8_t risk) {
  const char *bars[] = {
      "[----]", /* SAFE     */
      "[#---]", /* CAUTION  */
      "[##--]", /* WARNING  */
      "[####]", /* CRITICAL */
  };

  printf("> %4lu | %7.1fs | %6.3f | %5.2f | %6.3f%% | %s %s\r\n",
         (unsigned long)num, ts_ms / 1000.0f, ph_x1000 / 1000.0f,
         temp_x100 / 100.0f, nh3_x100000 / 1000.0f, bars[risk],
         risk_str(risk));
}

/* ── Wi-Fi Connection ─────────────────────────────────────────────────── */
static bool wifi_connect(void) {
  printf("# Connecting to Wi-Fi: %s ...\r\n", WIFI_SSID);
  if (cyw43_arch_wifi_connect_timeout_ms(WIFI_SSID, WIFI_PASSWORD,
                                         CYW43_AUTH_WPA2_AES_PSK,
                                         WIFI_CONNECT_TIMEOUT_MS) != 0) {
    printf("# [ERROR] Wi-Fi connection failed.\r\n");
    return false;
  }
  printf("# Wi-Fi connected! IP: %s\r\n",
         ip4addr_ntoa(netif_ip4_addr(netif_default)));
  return true;
}

/* ── TCP Socket Handle ────────────────────────────────────────────────── */
static int g_sock = -1;

static bool socket_connect(void) {
  g_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (g_sock < 0) {
    printf("# [ERROR] socket() failed\r\n");
    return false;
  }

  struct sockaddr_in server_addr;
  memset(&server_addr, 0, sizeof(server_addr));
  server_addr.sin_family = AF_INET;
  server_addr.sin_port = htons(N3IWF_PORT);
  ip4addr_aton(N3IWF_SERVER_IP, (ip4_addr_t *)&server_addr.sin_addr);

  printf("# Connecting to N3IWF Server %s:%d ...\r\n", N3IWF_SERVER_IP,
         N3IWF_PORT);
  if (connect(g_sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) !=
      0) {
    printf("# [ERROR] TCP connect failed.\r\n");
    closesocket(g_sock);
    g_sock = -1;
    return false;
  }

  /* Set recv timeout so it doesn't block the main loop */
  struct timeval tv = {.tv_sec = 0, .tv_usec = SOCKET_RECV_TIMEOUT_MS * 1000};
  setsockopt(g_sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

  printf("# N3IWF TCP connection established!\r\n");
  return true;
}

static void socket_disconnect(void) {
  if (g_sock >= 0) {
    closesocket(g_sock);
    g_sock = -1;
  }
}

/* ── Send DATA string via TCP ─────────────────────────────────────────── */
/* Returns false if socket is broken (caller should reconnect) */
static bool socket_send_data(int32_t ph_x1000, int32_t temp_x100,
                             uint8_t risk) {
  if (g_sock < 0)
    return false;

  char buf[64];
  snprintf(buf, sizeof(buf), "DATA:%ld,%ld,%u\n", (long)ph_x1000,
           (long)temp_x100, (unsigned)risk);

  int sent = send(g_sock, buf, strlen(buf), 0);
  if (sent < 0) {
    printf("# [ERROR] send() failed\r\n");
    return false;
  }

  return true;
}

/* ── Receive from TCP (non-blocking) ──────────────────────────────────── */
static char g_recv_buf[512];
static int g_recv_len = 0;

static void socket_recv_check(void) {
  if (g_sock < 0)
    return;

  char tmp[128];
  int n = recv(g_sock, tmp, sizeof(tmp) - 1, 0);
  if (n > 0) {
    /* Append to buffer */
    if (g_recv_len + n < (int)sizeof(g_recv_buf)) {
      memcpy(g_recv_buf + g_recv_len, tmp, n);
      g_recv_len += n;
      g_recv_buf[g_recv_len] = '\0';
    }
  } else if (n == 0) {
    /* Server closed connection */
    printf("# [WARN] N3IWF server disconnected.\r\n");
    socket_disconnect();
    return;
  }

  /* Process complete lines (for future Q-table support if needed) */
  char *nl;
  while ((nl = strchr(g_recv_buf, '\n')) != NULL) {
    *nl = '\0';
    printf("# [RX] %s\r\n", g_recv_buf);
    
    /* Shift remaining data */
    int consumed = (nl - g_recv_buf) + 1;
    g_recv_len -= consumed;
    memmove(g_recv_buf, nl + 1, g_recv_len);
    g_recv_buf[g_recv_len] = '\0';
  }
}

/* ══════════════════════════════════════════════════════════════════════ */
/*                              MAIN                                      */
/* ══════════════════════════════════════════════════════════════════════ */
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

  /* ── Initialize CYW43 (Wi-Fi chip) ────────────────────────────────── */
  if (cyw43_arch_init()) {
    printf("# [FATAL] cyw43_arch_init() failed\r\n");
    return 1;
  }
  cyw43_arch_enable_sta_mode();

  /* ── Initialize sensors ───────────────────────────────────────────── */
  ph_sensor_init();
  if (!ds18b20_init(TEMP_GPIO_PIN)) {
    printf("# [WARN] DS18B20 not detected on GPIO%d\r\n", TEMP_GPIO_PIN);
  }

  printf("# Sensors initialized.\r\n");
  printf("# \r\n");

  /* ── Connect Wi-Fi ────────────────────────────────────────────────── */
  while (!wifi_connect()) {
    printf("# Retrying Wi-Fi in 5s...\r\n");
    sleep_ms(5000);
  }

  /* ── Connect to N3IWF TCP Server ──────────────────────────────────── */
  while (!socket_connect()) {
    printf("# Retrying TCP connection in 5s...\r\n");
    sleep_ms(5000);
  }

  printf("# \r\n");
  printf("# Starting data stream...\r\n");
  printf("# \r\n");
  printf(">  Num |   Time  |   pH   | Temp°C |  NH3%%  | Risk\r\n");
  printf("> -----|---------|--------|--------|--------|---------------\r\n");

  uint32_t sample_num = 0;
  uint32_t last_sample_ms = 0;

  /* ══════════════════════════════════════════════════════════════════ */
  /*                          MAIN LOOP                                 */
  /* ══════════════════════════════════════════════════════════════════ */
  while (true) {
    uint32_t now_ms = to_ms_since_boot(get_absolute_time());

    /* ── Sample every SAMPLE_INTERVAL_MS ────────────────────────────── */
    if (now_ms - last_sample_ms >= SAMPLE_INTERVAL_MS) {
      last_sample_ms = now_ms;
      sample_num++;

      /* ── 1. Trigger DS18B20 conversion (750 ms for 12-bit) ────────── */
      ds18b20_convert(TEMP_GPIO_PIN);

      /* ── 2. Read pH sensor (parallel with DS18B20 conversion) ──────── */
      uint16_t adc_raw = ph_sensor_read_raw();
      int32_t ph_mv = ph_adc_to_mv(adc_raw);
      int32_t ph_x1000 = ph_mv_to_ph(ph_mv);

      /* ── 3. Wait for DS18B20 conversion to complete ────────────────── */
      sleep_ms(800);

      /* ── 4. Read temperature ───────────────────────────────────────── */
      int32_t temp_x100 = ds18b20_read_raw(TEMP_GPIO_PIN);

      /* ── 5. Calculate NH3 and risk level ───────────────────────────── */
      int32_t nh3_x100000 = calc_nh3_x100000(ph_x1000, temp_x100);
      uint8_t risk = calc_risk_level(nh3_x100000);

      /* ── 6. Send data to RPi5 via Wi-Fi TCP ────────────────────────── */
      /* Format: "DATA:ph_x1000,temp_x100,risk\n" */
      if (!socket_send_data(ph_x1000, temp_x100, risk)) {
        printf("# [WARN] TCP send failed — reconnecting...\r\n");
        socket_disconnect();
        while (!socket_connect()) {
          printf("# Retry TCP in 3s...\r\n");
          sleep_ms(3000);
        }
      }

      /* ── 7. Print to serial monitor ────────────────────────────────── */
      print_monitor(sample_num, now_ms, ph_x1000, temp_x100, nh3_x100000,
                    risk);
    }

    /* ── Check for incoming data (non-blocking) ───────────────────────── */
    socket_recv_check();

    /* ── Blink LED to show alive ──────────────────────────────────────── */
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, (now_ms / 500) % 2);

    /* ── Small delay to prevent busy-wait ─────────────────────────────── */
    sleep_ms(10);
  }

  /* Cleanup (never reached) */
  socket_disconnect();
  cyw43_arch_deinit();
  return 0;
}
