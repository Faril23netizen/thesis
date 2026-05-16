/*
 * Data Streaming Node — Raspberry Pi Pico WH (RP2040)
 * =====================================================
 * Thesis : Edge-Intelligent Aquaculture Aerator Control
 *          Using Progressive Hybrid FQL-DQN with N3IWF LES
 * Student: Faril Pirwanhadi (M14128104)
 * Advisor: Yi-Chih Tung, En-Cheng Liou
 *
 * Peran Pico dalam arsitektur:
 *   - Baca pH sensor + DS18B20 setiap 2 detik
 *   - Hitung NH3 dari pH + Temp
 *   - Stage 1: Rule-Based safety check → selalu aktif sebagai final gate
 *   - Stage 2: FQL/DQN inference lokal setelah Q-table diterima dari RPi5
 *   - Kirim data ke RPi5 via Wi-Fi TCP Socket (N3IWF LES)
 *   - Terima Q-table dari RPi5 via Wi-Fi TCP Socket
 *
 * Hardware:
 *   pH Sensor Module → ADC0 (GPIO26)
 *   DS18B20          → GPIO15, pull-up 4.7 kΩ ke 3.3 V
 *   Relay A          → GPIO16 (bit 0)
 *   Relay B          → GPIO17 (bit 1)
 *   Output           → Wi-Fi TCP Socket (N3IWF Local Edge Service)
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
#include "fql_inference.h"
#include "ph_sensor.h"


/* ── Wi-Fi & N3IWF Configuration ─────────────────────────────────────────── */
/* GANTI dengan SSID dan password jaringan Wi-Fi lokal di lokasi tambak       */
#define WIFI_SSID "N3IWF_AQUA"
#define WIFI_PASSWORD "skripsi2026"

/* IP Address Raspberry Pi 5 (N3IWF Edge Server) — sesuaikan dengan IP RPi5  */
#define N3IWF_SERVER_IP "10.42.0.1"
#define N3IWF_PORT 5005

/* Timeout koneksi Wi-Fi dan socket (ms) */
#define WIFI_CONNECT_TIMEOUT_MS 30000
#define SOCKET_RECV_TIMEOUT_MS 100

/* ── Pin & timing config ────────────────────────────────────────────────── */
#define TEMP_GPIO_PIN 15
#define RELAY_PIN_A 16 /* bit 0 — LOW/HIGH level  */
#define RELAY_PIN_B 17 /* bit 1 — MED/HIGH level  */
#define SAMPLE_INTERVAL_MS                                                     \
  2000 /* 2 detik — optimal untuk pH electrode                               \
        * stabilization + DS18B20 12-bit (750ms) */

/* ── Action codes (aerator level) ───────────────────────────────────────── */
#define ACTION_OFF 0
#define ACTION_LOW 1
#define ACTION_MED 2
#define ACTION_HIGH 3

/* ── NH3 chemistry (Eq. 2.1 & 2.2) ─────────────────────────────────────── */
static int32_t calc_nh3_x100000(int32_t ph_x1000, int32_t temp_x100) {
  float ph = ph_x1000 / 1000.0f;
  float temp = temp_x100 / 100.0f;
  float pka = 0.09018f + 2729.92f / (temp + 273.15f);
  float fnh3 = 1.0f / (1.0f + powf(10.0f, pka - ph));
  return (int32_t)(fnh3 * 100000.0f);
}

/* ── Stage 1: Rule-Based Safety → pilih action aerator ──────────────────── */
/*
 * Selalu aktif, tidak bisa di-override oleh FQL/DQN.
 * Menjadi final gate — jika kondisi DANGER, paksa HIGH tanpa tanya FQL.
 */
static uint8_t safety_action(int32_t ph_x1000, int32_t temp_x100) {
  if (ph_x1000 < 6000 || ph_x1000 > 9500)
    return ACTION_HIGH; /* DANGER_PH   */
  if (temp_x100 > 3500)
    return ACTION_HIGH; /* DANGER_TEMP */
  if (ph_x1000 < 6500 || ph_x1000 > 8500)
    return ACTION_MED; /* WARNING     */
  if (temp_x100 > 3000)
    return ACTION_MED; /* WARNING     */
  return ACTION_LOW;   /* SAFE        */
}

static const char *action_str(uint8_t a) {
  switch (a) {
  case ACTION_OFF:
    return "OFF ";
  case ACTION_LOW:
    return "LOW ";
  case ACTION_MED:
    return "MED ";
  case ACTION_HIGH:
    return "HIGH";
  default:
    return "?   ";
  }
}

/* ── Relay control (2-pin, 4 level) ─────────────────────────────────────── */
/*
 * 2-bit encoding:
 *   PIN_A  PIN_B  →  Level
 *     0      0   →  OFF
 *     1      0   →  LOW
 *     0      1   →  MED
 *     1      1   →  HIGH
 */
static void relay_set(uint8_t action) {
  gpio_put(RELAY_PIN_A,
           (action == ACTION_LOW || action == ACTION_HIGH) ? 1 : 0);
  gpio_put(RELAY_PIN_B,
           (action == ACTION_MED || action == ACTION_HIGH) ? 1 : 0);
}

/* ── Serial monitor display (visual, bukan untuk parsing RPi4) ───────────── */
static void print_monitor(uint32_t num, uint32_t ts_ms, int32_t ph_x1000,
                          int32_t temp_x100, int32_t nh3_x100000,
                          uint8_t action, const char *mode) {
  const char *bars[] = {
      "[----]", /* OFF  */
      "[#---]", /* LOW  */
      "[##--]", /* MED  */
      "[####]", /* HIGH */
  };
  const char *labels[] = {"OFF ", "LOW ", "MED ", "HIGH"};

  /* Status based on actual water conditions, not aerator action */
  const char *status;
  if (ph_x1000 < 6000 || ph_x1000 > 9500 || temp_x100 > 3500)
    status = "!! DANGER  !!";
  else if (ph_x1000 < 6500 || ph_x1000 > 8500 || temp_x100 > 3000)
    status = "~  WARNING  ~";
  else
    status = "   SAFE      ";

  printf("> #%04lu | %6.1fs | pH=%ld.%03ld | T=%ld.%02ldC | NH3=%ld.%03ld%% "
         "| AERATOR %s %s | %s | [%s]\r\n",
         (unsigned long)num, ts_ms / 1000.0f, (long)(ph_x1000 / 1000),
         (long)((ph_x1000 < 0 ? -ph_x1000 : ph_x1000) % 1000),
         (long)(temp_x100 / 100),
         (long)((temp_x100 < 0 ? -temp_x100 : temp_x100) % 100),
         (long)(nh3_x100000 / 1000), (long)(nh3_x100000 % 1000), bars[action],
         labels[action], status, mode);
}

/* ── Wi-Fi Connection ───────────────────────────────────────────────────── */
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

/* ── TCP Socket Handle (LwIP Raw API) ────────────────────────────────────── */
static struct tcp_pcb *g_tcp_pcb = NULL;
static bool g_is_connected = false;

static void socket_disconnect(void);

static err_t tcp_connected_cb(void *arg, struct tcp_pcb *tpcb, err_t err) {
  if (err == ERR_OK) {
    printf("# N3IWF TCP connection established!\r\n");
    g_is_connected = true;
  } else {
    printf("# [ERROR] TCP connect error: %d\r\n", err);
  }
  return err;
}

static void tcp_err_cb(void *arg, err_t err) {
  printf("# [ERROR] TCP connection fatal error: %d\r\n", err);
  g_is_connected = false;
  if (g_tcp_pcb) {
    tcp_close(g_tcp_pcb);
    g_tcp_pcb = NULL;
  }
}

static char g_recv_buf[4096];
static int g_recv_len = 0;

static err_t tcp_recv_cb(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err) {
  if (p == NULL) {
    printf("# [WARN] TCP connection closed by server.\r\n");
    g_is_connected = false;
    tcp_close(tpcb);
    g_tcp_pcb = NULL;
    return ERR_OK;
  }
  
  /* Copy received data to buffer */
  int copy_len = p->tot_len;
  if (g_recv_len + copy_len > sizeof(g_recv_buf) - 1) {
      copy_len = sizeof(g_recv_buf) - 1 - g_recv_len;
  }
  pbuf_copy_partial(p, g_recv_buf + g_recv_len, copy_len, 0);
  g_recv_len += copy_len;
  g_recv_buf[g_recv_len] = '\0';
  
  tcp_recved(tpcb, p->tot_len);
  pbuf_free(p);
  return ERR_OK;
}

static bool socket_connect(void) {
  if (g_is_connected) return true;

  ip_addr_t server_ip;
  ipaddr_aton(N3IWF_SERVER_IP, &server_ip);

  printf("# Connecting to N3IWF Server %s:%d ...\r\n", N3IWF_SERVER_IP, N3IWF_PORT);
  
  cyw43_arch_lwip_begin();
  if (!g_tcp_pcb) {
    g_tcp_pcb = tcp_new_ip_type(IPADDR_TYPE_ANY);
    tcp_err(g_tcp_pcb, tcp_err_cb);
    tcp_recv(g_tcp_pcb, tcp_recv_cb);
  }
  err_t err = tcp_connect(g_tcp_pcb, &server_ip, N3IWF_PORT, tcp_connected_cb);
  cyw43_arch_lwip_end();

  if (err != ERR_OK) {
    printf("# [ERROR] TCP connect failed to start (err=%d).\r\n", err);
    socket_disconnect();
    return false;
  }

  /* Wait for connection to establish */
  for(int i=0; i<30 && !g_is_connected && g_tcp_pcb; i++) {
    sleep_ms(100);
  }
  
  if (!g_is_connected) {
    printf("# [WARN] TCP connection timeout.\r\n");
    socket_disconnect();
  }
  
  return g_is_connected;
}

static void socket_disconnect(void) {
  g_is_connected = false;
  if (g_tcp_pcb) {
    cyw43_arch_lwip_begin();
    tcp_close(g_tcp_pcb);
    g_tcp_pcb = NULL;
    cyw43_arch_lwip_end();
  }
}

/* ── Send DATA string via TCP ───────────────────────────────────────────── */
static bool socket_send_data(int32_t ph_x1000, int32_t temp_x100, uint8_t action) {
  if (!g_is_connected || !g_tcp_pcb) return false;
  
  char buf[64];
  int len = snprintf(buf, sizeof(buf), "DATA:%ld,%ld,%u\n", (long)ph_x1000, (long)temp_x100, (unsigned)action);
  
  cyw43_arch_lwip_begin();
  err_t err = tcp_write(g_tcp_pcb, buf, len, TCP_WRITE_FLAG_COPY);
  if (err == ERR_OK) {
    tcp_output(g_tcp_pcb);
  }
  cyw43_arch_lwip_end();
  
  return err == ERR_OK;
}

/* ── Receive & parse Q-table from TCP ──────────────────────────────────── */
static void check_wifi_input(FQL_QTable_t *qt) {
  if (!g_is_connected || g_recv_len == 0) return;

  char *nl = strchr(g_recv_buf, '\n');
  if (!nl) return;   /* not a complete line yet */
  
  *nl = '\0'; /* terminate the line      */

  if (strncmp(g_recv_buf, "QTABLE:", 7) == 0) {
    if (fql_parse_qtable(g_recv_buf, qt)) {
      printf("# [OK] Q-table loaded (%d rules x %d actions)\r\n", FQL_N_RULES, FQL_N_ACTIONS);
      cyw43_arch_lwip_begin();
      tcp_write(g_tcp_pcb, "ACK:QTABLE_LOADED\n", 18, TCP_WRITE_FLAG_COPY);
      tcp_output(g_tcp_pcb);
      cyw43_arch_lwip_end();
    } else {
      printf("# [ERROR] Q-table parse failed.\r\n");
      cyw43_arch_lwip_begin();
      tcp_write(g_tcp_pcb, "ACK:QTABLE_ERROR\n", 17, TCP_WRITE_FLAG_COPY);
      tcp_output(g_tcp_pcb);
      cyw43_arch_lwip_end();
    }
  } else {
    printf("# [WARN] unknown command: %s\r\n", g_recv_buf);
  }

  /* Shift remaining bytes */
  int remaining = g_recv_len - (int)(nl - g_recv_buf) - 1;
  if (remaining > 0) memmove(g_recv_buf, nl + 1, remaining);
  g_recv_len = remaining > 0 ? remaining : 0;
}

/* ── main ───────────────────────────────────────────────────────────────── */
int main(void) {
  stdio_init_all();
  cyw43_arch_init();

  /* Init relay pins */
  gpio_init(RELAY_PIN_A);
  gpio_set_dir(RELAY_PIN_A, GPIO_OUT);
  gpio_put(RELAY_PIN_A, 0);
  gpio_init(RELAY_PIN_B);
  gpio_set_dir(RELAY_PIN_B, GPIO_OUT);
  gpio_put(RELAY_PIN_B, 0);

  /* Init sensor */
  ph_sensor_init();

  DS18B20_t ds_dev;
  if (!ds18b20_init(&ds_dev, TEMP_GPIO_PIN)) {
    printf("[ERROR] DS18B20 tidak terdeteksi pada GPIO%d\r\n", TEMP_GPIO_PIN);
    while (true)
      tight_loop_contents();
  }

  /* Inisialisasi Q-table (belum loaded, pakai Rule-Based dulu) */
  FQL_QTable_t qt = {.loaded = false};

  /* Print header sekali */
  printf("# ============================================================\r\n");
  printf("# Pico WH — Aquaculture N3IWF Edge Node\r\n");
  printf("# DS18B20 ROM: %02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X\r\n",
         ds_dev.rom[0], ds_dev.rom[1], ds_dev.rom[2], ds_dev.rom[3],
         ds_dev.rom[4], ds_dev.rom[5], ds_dev.rom[6], ds_dev.rom[7]);
  printf("# interval=%d ms | relayA=GPIO%d | relayB=GPIO%d\r\n",
         SAMPLE_INTERVAL_MS, RELAY_PIN_A, RELAY_PIN_B);
  printf("# Aerator levels: [----]=OFF [#---]=LOW [##--]=MED [####]=HIGH\r\n");
  printf("# Menghubungkan ke N3IWF Server: %s:%d\r\n", N3IWF_SERVER_IP,
         N3IWF_PORT);
  printf("# ============================================================\r\n");

  /* ── Connect Wi-Fi ─────────────────────────────────────────────────── */
  while (!wifi_connect()) {
    printf("# Retrying Wi-Fi in 5s...\r\n");
    sleep_ms(5000);
  }

  /* ── Connect to N3IWF TCP Server ───────────────────────────────────── */
  while (!socket_connect()) {
    printf("# Retrying TCP connection in 5s...\r\n");
    sleep_ms(5000);
  }

  uint32_t start_ms = to_ms_since_boot(get_absolute_time());
  uint32_t record_num = 0;

  /* pH median filter — 3-sample buffer, rejects ADC noise spikes */
  int32_t ph_buf[3] = {7000, 7000, 7000};
  uint8_t ph_buf_i = 0;

  while (true) {
    uint32_t loop_start = to_ms_since_boot(get_absolute_time());

    /* ── 1. Baca sensor ─────────────────────────────────────────── */
    ds18b20_convert(&ds_dev);

    uint16_t adc_raw = ph_sensor_read_raw();
    int32_t ph_mv = ph_adc_to_mv(adc_raw);
    int32_t ph_raw = ph_mv_to_ph(ph_mv, &PH_CAL_DEFAULT);

    /* Median filter: store sample, sort copy of 3, pick middle */
    ph_buf[ph_buf_i++ % 3] = ph_raw;
    int32_t s[3] = {ph_buf[0], ph_buf[1], ph_buf[2]};
    /* Simple 3-element sort */
    if (s[0] > s[1]) {
      int32_t t = s[0];
      s[0] = s[1];
      s[1] = t;
    }
    if (s[1] > s[2]) {
      int32_t t = s[1];
      s[1] = s[2];
      s[2] = t;
    }
    if (s[0] > s[1]) {
      int32_t t = s[0];
      s[0] = s[1];
      s[1] = t;
    }
    int32_t ph_x1000 = s[1]; /* median */

    /* Tunggu sisa konversi DS18B20 (750 ms total) */
    uint32_t elapsed = to_ms_since_boot(get_absolute_time()) - loop_start;
    if (elapsed < 760)
      sleep_ms(760 - elapsed);

    int32_t temp_x100 = ds18b20_read_raw(&ds_dev);
    if (temp_x100 == INT32_MIN) {
      printf("# [WARN] CRC error DS18B20, skip record %lu\r\n",
             (unsigned long)record_num);
      continue;
    }

    /* ── 2. Hitung NH3 ──────────────────────────────────────────── */
    int32_t nh3_x100000 = calc_nh3_x100000(ph_x1000, temp_x100);

    /* ── 3. Tentukan action ─────────────────────────────────────── */
    uint8_t action;
    const char *mode;
    bool is_danger = (ph_x1000 < 6000 || ph_x1000 > 9500 || temp_x100 > 3500);

    if (is_danger) {
      /* DANGER: Rule-Based paksa HIGH, FQL tidak dipakai */
      action = ACTION_HIGH;
      mode = "RB!"; /* Rule-Based forced (danger override) */
    } else if (qt.loaded) {
      /* AMAN + Q-table sudah ada: pakai FQL inference */
      action = fql_select_action(ph_x1000, temp_x100, &qt);
      mode = "FQL"; /* Fuzzy Q-Learning inference */
    } else {
      /* AMAN + Q-table belum ada: pakai Rule-Based */
      action = safety_action(ph_x1000, temp_x100);
      mode = "RB "; /* Rule-Based (waiting for Q-table) */
    }

    /* ── 4. Eksekusi relay ──────────────────────────────────────── */
    relay_set(action);
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, action != ACTION_OFF ? 1 : 0);

    uint32_t ts_ms = to_ms_since_boot(get_absolute_time()) - start_ms;

    /* ── 5. Monitor line (visual, untuk serial monitor) ─────────── */
    print_monitor(record_num, ts_ms, ph_x1000, temp_x100, nh3_x100000, action,
                  mode);

    /* ── 6. Kirim data ke RPi5 via Wi-Fi TCP ────────────────────── */
    /* Format: "DATA:ph_x1000,temp_x100,action\n" */
    if (!socket_send_data(ph_x1000, temp_x100, action)) {
      printf("# [WARN] TCP send failed — reconnecting...\r\n");
      socket_disconnect();
      while (!socket_connect()) {
        printf("# Retry TCP in 3s...\r\n");
        sleep_ms(3000);
      }
    }

    /* ── 7. Cek input Wi-Fi (terima Q-table dari RPi5) ──────────── */
    check_wifi_input(&qt);

    record_num++;

    /* ── Tunggu interval berikutnya ─────────────────────────────── */
    uint32_t loop_dur = to_ms_since_boot(get_absolute_time()) - loop_start;
    if (loop_dur < SAMPLE_INTERVAL_MS)
      sleep_ms(SAMPLE_INTERVAL_MS - loop_dur);
  }
}
