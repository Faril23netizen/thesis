#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "lwip/pbuf.h"
#include "lwip/tcp.h"

#define TCP_PORT N3IWF_PORT

struct tcp_pcb *g_tcp_pcb = NULL;
bool g_is_connected = false;

static err_t tcp_connected_cb(void *arg, struct tcp_pcb *tpcb, err_t err) {
    if (err == ERR_OK) {
        printf("# N3IWF TCP connection established!\r\n");
        g_is_connected = true;
    } else {
        printf("# [ERROR] TCP connect error: %d\r\n", err);
    }
    return err;
}

static err_t tcp_recv_cb(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err) {
    if (p == NULL) {
        printf("# [WARN] TCP connection closed by server.\r\n");
        g_is_connected = false;
        tcp_close(tpcb);
        g_tcp_pcb = NULL;
        return ERR_OK;
    }
    tcp_recved(tpcb, p->tot_len);
    pbuf_free(p);
    return ERR_OK;
}

static void tcp_err_cb(void *arg, err_t err) {
    printf("# [ERROR] TCP connection fatal error: %d\r\n", err);
    g_is_connected = false;
    if (g_tcp_pcb) {
        tcp_close(g_tcp_pcb);
        g_tcp_pcb = NULL;
    }
}

int main(void) {
    stdio_init_all();
    sleep_ms(2000); /* Delay for USB CDC */

    printf("==========================================\n");
    printf(" Pico N3IWF Simple TCP Test\n");
    printf("==========================================\n");

    if (cyw43_arch_init()) {
        printf("# [FATAL] cyw43_arch_init() failed!\r\n");
        while (1) tight_loop_contents();
    }

    cyw43_arch_enable_sta_mode();

    printf("# Connecting to Wi-Fi: %s ...\r\n", WIFI_SSID);
    while (cyw43_arch_wifi_connect_timeout_ms(WIFI_SSID, WIFI_PASSWORD, CYW43_AUTH_WPA2_AES_PSK, 10000)) {
        printf("# [ERROR] Wi-Fi connection failed. Retrying in 5s...\r\n");
        sleep_ms(5000);
    }
    
    printf("# Wi-Fi connected! Connecting to N3IWF Server %s:%d ...\r\n", N3IWF_SERVER_IP, TCP_PORT);

    ip_addr_t server_ip;
    ipaddr_aton(N3IWF_SERVER_IP, &server_ip);

    cyw43_arch_lwip_begin();
    g_tcp_pcb = tcp_new_ip_type(IPADDR_TYPE_ANY);
    tcp_err(g_tcp_pcb, tcp_err_cb);
    tcp_recv(g_tcp_pcb, tcp_recv_cb);
    tcp_connect(g_tcp_pcb, &server_ip, TCP_PORT, tcp_connected_cb);
    cyw43_arch_lwip_end();

    int count = 1;
    bool led_state = false;
    
    while (1) {
        // Toggle LED based on connection status
        led_state = !led_state;
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, led_state);

        if (g_is_connected && g_tcp_pcb) {
            char buffer[64];
            int len = snprintf(buffer, sizeof(buffer), "TEST_DATA: seq=%d, status=OK\n", count++);
            
            cyw43_arch_lwip_begin();
            err_t err = tcp_write(g_tcp_pcb, buffer, len, TCP_WRITE_FLAG_COPY);
            if (err == ERR_OK) {
                tcp_output(g_tcp_pcb);
                printf("# Sent: %s", buffer);
            } else {
                printf("# [ERROR] TCP write failed: %d\r\n", err);
            }
            cyw43_arch_lwip_end();
            
            // Slow blink (connected)
            sleep_ms(2000); 
        } else {
            // Fast blink (disconnected / waiting)
            sleep_ms(200);
        }
    }

    return 0;
}
