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

/* ── Q-table storage ─────────────────────────────────────────────────────── */
#define QTABLE_ROWS 9
#define QTABLE_COLS 4
static float g_qtable[QTABLE_ROWS][QTABLE_COLS];
static bool g_qtable_loaded = false;

/* ── Receive buffer ──────────────────────────────────────────────────────── */
static char g_recv_buf[2048];
static int g_recv_len = 0;

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

/* ── Q-table parsing ─────────────────────────────────────────────────────── */
static bool parse_qtable(const char *line) {
    /* Expected format: QTABLE:[[row0],[row1],...,[row8]] */
    if (strncmp(line, "QTABLE:", 7) != 0) {
        return false;
    }
    
    const char *p = line + 7;
    
    /* Skip opening [[ */
    while (*p && (*p == '[' || *p == ' ')) p++;
    
    /* Parse 9 rows x 4 cols */
    for (int i = 0; i < QTABLE_ROWS; i++) {
        for (int j = 0; j < QTABLE_COLS; j++) {
            /* Skip whitespace and commas */
            while (*p && (*p == ' ' || *p == ',' || *p == '[')) p++;
            
            /* Parse float */
            char *endp;
            g_qtable[i][j] = strtof(p, &endp);
            if (p == endp) {
                printf("# [ERROR] Q-table parse failed at [%d][%d]\n", i, j);
                return false;
            }
            p = endp;
            
            /* Skip closing bracket */
            while (*p && (*p == ' ' || *p == ']')) p++;
        }
    }
    
    g_qtable_loaded = true;
    printf("# Q-table loaded successfully\n");
    return true;
}

static uint8_t qtable_predict_risk(int32_t ph_x1000, int32_t temp_x100) {
    if (!g_qtable_loaded) {
        /* Fallback to rule-based */
        return calc_risk_level(calc_nh3_x100000(ph_x1000, temp_x100));
    }
    
    /* Fuzzy state mapping (simplified) */
    /* pH zones: VeryAcid(<6.0), Acidic(6.0-6.5), Normal(6.5-8.5), Alkaline(8.5-9.5), VeryAlk(>9.5) */
    /* Temp zones: VCold(<20), Cold(20-25), Opt(25-30), Hot(30-35), VHot(>35) */
    
    int ph_zone = 2; /* Default: Normal */
    if (ph_x1000 < 6000) ph_zone = 0;
    else if (ph_x1000 < 6500) ph_zone = 1;
    else if (ph_x1000 <= 8500) ph_zone = 2;
    else if (ph_x1000 <= 9500) ph_zone = 3;
    else ph_zone = 4;
    
    int temp_zone = 2; /* Default: Opt */
    if (temp_x100 < 2000) temp_zone = 0;
    else if (temp_x100 < 2500) temp_zone = 1;
    else if (temp_x100 <= 3000) temp_zone = 2;
    else if (temp_x100 <= 3500) temp_zone = 3;
    else temp_zone = 4;
    
    /* Map to Q-table index (5 pH zones × 5 temp zones = 25 states, but we have 9x4 Q-table) */
    /* Simplified mapping: use pH zone as row (0-4 mapped to 0-8), temp zone as col (0-4 mapped to 0-3) */
    int row = (ph_zone * 9) / 5; /* Scale 0-4 to 0-8 */
    int col = (temp_zone * 4) / 5; /* Scale 0-4 to 0-3 */
    
    if (row >= QTABLE_ROWS) row = QTABLE_ROWS - 1;
    if (col >= QTABLE_COLS) col = QTABLE_COLS - 1;
    
    /* Find action with max Q-value */
    float max_q = g_qtable[row][0];
    uint8_t best_risk = 0;
    for (int a = 1; a < QTABLE_COLS; a++) {
        if (g_qtable[row][a] > max_q) {
            max_q = g_qtable[row][a];
            best_risk = a;
        }
    }
    
    return best_risk;
}

/* ── TCP callbacks ───────────────────────────────────────────────────────── */
static err_t tcp_client_recv(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err) {
    tcp_client_t *state = (tcp_client_t*)arg;
    
    if (!p) {
        /* Connection closed */
        printf("# Connection closed by server\n");
        tcp_client_close(state);
        return ERR_OK;
    }
    
    if (err != ERR_OK) {
        pbuf_free(p);
        return err;
    }
    
    /* Copy data to receive buffer */
    if (g_recv_len + p->tot_len < sizeof(g_recv_buf) - 1) {
        pbuf_copy_partial(p, g_recv_buf + g_recv_len, p->tot_len, 0);
        g_recv_len += p->tot_len;
        g_recv_buf[g_recv_len] = '\0';
    }
    
    /* Process complete lines */
    char *nl;
    while ((nl = strchr(g_recv_buf, '\n')) != NULL) {
        *nl = '\0';
        
        /* Check if it's a Q-table */
        if (strncmp(g_recv_buf, "QTABLE:", 7) == 0) {
            printf("# Receiving Q-table...\n");
            if (parse_qtable(g_recv_buf)) {
                /* Send ACK */
                const char *ack = "ACK:QTABLE_LOADED\n";
                cyw43_arch_lwip_begin();
                tcp_write(tpcb, ack, strlen(ack), TCP_WRITE_FLAG_COPY);
                tcp_output(tpcb);
                cyw43_arch_lwip_end();
                printf("# ACK sent\n");
            } else {
                /* Send error ACK */
                const char *ack = "ACK:QTABLE_ERROR\n";
                cyw43_arch_lwip_begin();
                tcp_write(tpcb, ack, strlen(ack), TCP_WRITE_FLAG_COPY);
                tcp_output(tpcb);
                cyw43_arch_lwip_end();
                printf("# ACK error sent\n");
            }
        } else {
            printf("# [RX] %s\n", g_recv_buf);
        }
        
        /* Shift remaining data */
        int consumed = (nl - g_recv_buf) + 1;
        g_recv_len -= consumed;
        memmove(g_recv_buf, nl + 1, g_recv_len);
        g_recv_buf[g_recv_len] = '\0';
    }
    
    tcp_recved(tpcb, p->tot_len);
    pbuf_free(p);
    return ERR_OK;
}

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
    tcp_recv(state->tcp_pcb, tcp_client_recv);

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
  printf("# Initializing pH sensor...\r\n");
  ph_sensor_init();
  printf("# pH sensor OK\r\n");
  
  printf("# Initializing DS18B20 on GPIO%d...\r\n", TEMP_GPIO_PIN);
  if (!ds18b20_init(&g_ds18b20, TEMP_GPIO_PIN)) {
    printf("# [WARN] DS18B20 not detected - will use dummy data\r\n");
  } else {
    printf("# DS18B20 OK\r\n");
  }

  printf("# Sensors initialized.\r\n");
  printf("# \r\n");

  /* ── Connect Wi-Fi ────────────────────────────────────────────────────── */
  printf("# Connecting to Wi-Fi: %s ...\r\n", WIFI_SSID);
  int wifi_retry = 0;
  while (cyw43_arch_wifi_connect_timeout_ms(WIFI_SSID, WIFI_PASSWORD,
                                            CYW43_AUTH_WPA2_AES_PSK,
                                            30000) != 0) {
    wifi_retry++;
    printf("# Wi-Fi connection failed (attempt %d), retrying in 5s...\r\n", wifi_retry);
    sleep_ms(5000);
    if (wifi_retry >= 10) {
      printf("# [ERROR] Wi-Fi connection failed after 10 attempts\r\n");
      printf("# Check: SSID=%s, Password=%s\r\n", WIFI_SSID, WIFI_PASSWORD);
      printf("# Continuing anyway for testing...\r\n");
      break;
    }
  }
  
  if (wifi_retry < 10) {
    printf("# Wi-Fi connected! IP: %s\r\n",
           ip4addr_ntoa(netif_ip4_addr(netif_default)));
  }

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
      /* Sanity check */
      if (ph_x1000 < 0 || ph_x1000 > 14000) {
        printf("# [WARN] Invalid pH reading: %ld, using default\r\n", (long)ph_x1000);
        ph_x1000 = 7000; /* Default pH 7.0 */
      }

      /* ── 3. Wait for DS18B20 conversion to complete ────────────────────── */
      sleep_ms(800);

      /* ── 4. Read temperature ───────────────────────────────────────────── */
      int32_t temp_x100 = 2500; /* Default 25°C if sensor fails */
      if (g_ds18b20.found) {
        temp_x100 = ds18b20_read_raw(&g_ds18b20);
        /* Sanity check */
        if (temp_x100 < -5000 || temp_x100 > 8500) {
          printf("# [WARN] Invalid temp reading: %ld, using default\r\n", (long)temp_x100);
          temp_x100 = 2500;
        }
      }

      /* ── 5. Calculate NH3 and risk level ───────────────────────────────── */
      int32_t nh3_x100000 = calc_nh3_x100000(ph_x1000, temp_x100);
      
      /* Use Q-table if loaded, otherwise use rule-based */
      uint8_t risk;
      if (g_qtable_loaded) {
        risk = qtable_predict_risk(ph_x1000, temp_x100);
      } else {
        risk = calc_risk_level(nh3_x100000);
      }

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
      const char *mode = g_qtable_loaded ? "FQL" : "RB";
      printf("> %4lu | %7.1fs | %6.3f | %5.2f | %6.3f%% | %s %s (%s)\r\n",
             (unsigned long)sample_num, now_ms / 1000.0f, ph_x1000 / 1000.0f,
             temp_x100 / 100.0f, nh3_x100000 / 1000.0f, bars[risk],
             risk_str(risk), mode);
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
