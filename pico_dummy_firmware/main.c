/**
 * Dummy Network Payload Node — Raspberry Pi Pico WH (RP2040)
 * ==========================================================
 * Thesis : Edge-Intelligent Aquaculture NH3 Risk Monitoring
 * Student: Faril Pirwanhadi (M14128104)
 *
 * Purpose: Acts as Node 2 (and 3) to generate network QoS traffic.
 * Does NOT read real sensors. Emits DUMMY:... payload to server.
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include "lwip/pbuf.h"
#include "lwip/tcp.h"

#define WIFI_SSID "N3IWF_AQUA"
#define WIFI_PASSWORD "skripsi2026"
#define N3IWF_SERVER_IP "10.42.0.1"
#define N3IWF_PORT 5000

#define SAMPLE_INTERVAL_MS 2000

static char g_recv_buf[2048];
static int g_recv_len = 0;

typedef struct {
    struct tcp_pcb *tcp_pcb;
    ip_addr_t remote_addr;
    bool connected;
} tcp_client_t;

static tcp_client_t *g_client = NULL;

static err_t tcp_client_close(tcp_client_t *state) {
    if (!state) return ERR_OK;
    printf("> Dummy Node disconnected from N3IWF.\n");
    if (state->tcp_pcb) {
        tcp_arg(state->tcp_pcb, NULL);
        tcp_poll(state->tcp_pcb, NULL, 0);
        tcp_sent(state->tcp_pcb, NULL);
        tcp_recv(state->tcp_pcb, NULL);
        tcp_err(state->tcp_pcb, NULL);
        err_t err = tcp_close(state->tcp_pcb);
        if (err != ERR_OK) {
            tcp_abort(state->tcp_pcb);
            return ERR_ABRT;
        }
        state->tcp_pcb = NULL;
    }
    state->connected = false;
    return ERR_OK;
}

static err_t tcp_client_recv(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err) {
    tcp_client_t *state = (tcp_client_t*)arg;
    if (!p) {
        tcp_client_close(state);
        return ERR_OK;
    }
    tcp_recved(tpcb, p->tot_len);
    
    // Read and ignore QTABLE to prove network traffic happened
    int len = p->tot_len;
    if (g_recv_len + len < sizeof(g_recv_buf) - 1) {
        pbuf_copy_partial(p, g_recv_buf + g_recv_len, len, 0);
        g_recv_len += len;
        g_recv_buf[g_recv_len] = '\0';
        
        char *line_end = strchr(g_recv_buf, '\n');
        while (line_end != NULL) {
            *line_end = '\0';
            
            if (strncmp(g_recv_buf, "QTABLE:", 7) == 0) {
                printf("> Received Q-Table update from server (load ignored).\n");
            }
            
            int remaining = g_recv_len - ((line_end - g_recv_buf) + 1);
            if (remaining > 0) {
                memmove(g_recv_buf, line_end + 1, remaining);
                g_recv_len = remaining;
                g_recv_buf[g_recv_len] = '\0';
            } else {
                g_recv_len = 0;
            }
            line_end = strchr(g_recv_buf, '\n');
        }
    } else {
        g_recv_len = 0; // buffer overflow reset
    }
    
    pbuf_free(p);
    return ERR_OK;
}

static void tcp_client_err(void *arg, err_t err) {
    printf("> TCP Connection error: %d\n", err);
    if (arg) {
        tcp_client_close((tcp_client_t*)arg);
    }
}

static err_t tcp_client_connected(void *arg, struct tcp_pcb *tpcb, err_t err) {
    tcp_client_t *state = (tcp_client_t*)arg;
    if (err != ERR_OK) {
        printf("> TCP Connection failed\n");
        tcp_client_close(state);
        return err;
    }
    printf("> Dummy Node Connected to N3IWF Edge Server!\n");
    state->connected = true;
    return ERR_OK;
}

static bool tcp_client_open() {
    printf("> Connecting to %s:%d...\n", N3IWF_SERVER_IP, N3IWF_PORT);
    
    if (!g_client) {
        g_client = calloc(1, sizeof(tcp_client_t));
    }
    g_client->connected = false;
    
    if (!ipaddr_aton(N3IWF_SERVER_IP, &g_client->remote_addr)) {
        printf("> Invalid IP\n");
        return false;
    }
    
    g_client->tcp_pcb = tcp_new();
    if (!g_client->tcp_pcb) {
        printf("> Error creating PCB\n");
        return false;
    }
    
    tcp_arg(g_client->tcp_pcb, g_client);
    tcp_err(g_client->tcp_pcb, tcp_client_err);
    tcp_recv(g_client->tcp_pcb, tcp_client_recv);
    
    err_t err = tcp_connect(g_client->tcp_pcb, &g_client->remote_addr, N3IWF_PORT, tcp_client_connected);
    if (err != ERR_OK) {
        printf("> Error tcp_connect %d\n", err);
        return false;
    }
    return true;
}

static void led_blink(int times, int on_ms, int off_ms) {
    for (int i = 0; i < times; i++) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        sleep_ms(on_ms);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        sleep_ms(off_ms);
    }
}

int main() {
    stdio_init_all();
    sleep_ms(2000); // wait for USB serial to settle

    printf("\n=== DUMMY NODE (QoS Traffic Generator) ===\n");
    printf("Board: Pico 2W (RP2350)\n");

    if (cyw43_arch_init()) {
        printf("Wi-Fi init FAILED - check firmware target is pico2_w\n");
        while (true) { led_blink(5, 100, 100); sleep_ms(500); }
    }

    cyw43_arch_enable_sta_mode();

    // Retry WiFi connect indefinitely (slow blink while trying)
    int attempt = 0;
    while (true) {
        attempt++;
        printf("[%d] Connecting to '%s'...\n", attempt, WIFI_SSID);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);

        int rc = cyw43_arch_wifi_connect_timeout_ms(
            WIFI_SSID, WIFI_PASSWORD, CYW43_AUTH_WPA2_AES_PSK, 15000);

        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);

        if (rc == 0) {
            break; // connected
        }
        printf("[%d] Failed (rc=%d), retry in 5s...\n", attempt, rc);
        led_blink(3, 200, 200); // 3 quick blinks = failed, retrying
        sleep_ms(5000);
    }

    printf("Connected! IP: %s\n", ip4addr_ntoa(netif_ip4_addr(netif_list)));
    led_blink(5, 100, 100); // 5 quick blinks = success!
    
    // Seed with boot time so each power-cycle gives unique random sequence
    srand((unsigned int)to_ms_since_boot(get_absolute_time()));

    // Initial walk position — randomized so Pico 2 and Pico 3 start differently
    float ph_walk   = 6.5f + (float)(rand() % 301) * 0.01f;  // 6.5 - 9.5
    float temp_walk = 20.0f + (float)(rand() % 1801) * 0.01f; // 20.0 - 38.0

    uint32_t last_sample_time = to_ms_since_boot(get_absolute_time());

    while (true) {
        cyw43_arch_poll();

        if (!g_client || !g_client->connected) {
            tcp_client_open();
            sleep_ms(2000);
            continue;
        }

        uint32_t now = to_ms_since_boot(get_absolute_time());
        if (now - last_sample_time >= SAMPLE_INTERVAL_MS) {
            last_sample_time = now;

            // Random walk: small drift each step → values slowly vary over time
            ph_walk   += ((float)(rand() % 101) - 50) * 0.001f; // ±0.05 per step
            temp_walk += ((float)(rand() % 101) - 50) * 0.006f; // ±0.30 per step
            if (ph_walk   < 6.5f)  ph_walk   = 6.5f;
            if (ph_walk   > 9.5f)  ph_walk   = 9.5f;
            if (temp_walk < 20.0f) temp_walk = 20.0f;
            if (temp_walk > 38.0f) temp_walk = 38.0f;

            char msg[128];
            int ph_sim   = (int)(ph_walk   * 1000.0f);
            int temp_sim = (int)(temp_walk * 100.0f);

            snprintf(msg, sizeof(msg), "DUMMY:%d,%d,0\n", ph_sim, temp_sim);
            
            cyw43_arch_lwip_begin();
            err_t err = tcp_write(g_client->tcp_pcb, msg, strlen(msg), TCP_WRITE_FLAG_COPY);
            if (err == ERR_OK) {
                tcp_output(g_client->tcp_pcb);
                printf("> Sent DUMMY payload: %s", msg);
            } else {
                printf("> Send failed: %d\n", err);
            }
            cyw43_arch_lwip_end();
            
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
            sleep_ms(50);
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        }
        sleep_ms(10);
    }
    
    cyw43_arch_deinit();
    return 0;
}
