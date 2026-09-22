/* SPDX-License-Identifier: MIT */
/* Diagnostic-only adapter for badjeff/zmk-pmw3610-driver at e970029.
 * No replacement sensor initialization or concurrent SPI access is introduced.
 * Sensor reads and state snapshots run on the same system workqueue as its driver.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/input/input.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include "pixart.h"

static const struct device *const sensor = DEVICE_DT_GET(DT_NODELABEL(trackball));
static const struct device *const console = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static atomic_t poll_enabled, work_ticks, poll_requests, poll_submit_rc;
static atomic_t sensor_ready, init_step, init_error;
static atomic_t motion_raw, irq_count, irq_monitor_rc;
static atomic_t id_rc, product_id;
static atomic_t input_events, last_x, last_y;
static struct gpio_callback irq_monitor;

static void count_irq(const struct device *port, struct gpio_callback *cb, uint32_t pins) {
    ARG_UNUSED(port);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    atomic_inc(&irq_count);
}

static void count_input(struct input_event *event, void *user_data) {
    ARG_UNUSED(user_data);
    atomic_inc(&input_events);
    if (event->type == INPUT_EV_REL && event->code == INPUT_REL_X) {
        atomic_set(&last_x, event->value);
    }
    if (event->type == INPUT_EV_REL && event->code == INPUT_REL_Y) {
        atomic_set(&last_y, event->value);
    }
}
INPUT_CALLBACK_DEFINE(DEVICE_DT_GET(DT_NODELABEL(trackball)), count_input, NULL);

static void probe_work_handler(struct k_work *work);
K_WORK_DELAYABLE_DEFINE(probe_work, probe_work_handler);

static void probe_work_handler(struct k_work *work) {
    ARG_UNUSED(work);
    const struct pixart_config *cfg = sensor->config;
    struct pixart_data *data = sensor->data;
    atomic_inc(&work_ticks);
    atomic_set(&sensor_ready, data->ready);
    atomic_set(&init_step, data->async_init_step);
    atomic_set(&init_error, data->err);
    if (device_is_ready(cfg->irq_gpio.port)) {
        atomic_set(&motion_raw, gpio_pin_get_raw(cfg->irq_gpio.port, cfg->irq_gpio.pin));
    }

    /* ID reads do not consume motion. Run after async init finishes or fails,
     * never during its power-up sequence. SPI accesses stay on its workqueue.
     */
    if ((data->ready || data->err) && atomic_get(&work_ticks) % 50 == 0) {
        uint8_t address = 0x00, value = 0;
        const struct spi_buf tx_buf = {.buf = &address, .len = 1};
        const struct spi_buf_set tx = {.buffers = &tx_buf, .count = 1};
        struct spi_buf rx_bufs[] = {{.buf = NULL, .len = 1}, {.buf = &value, .len = 1}};
        const struct spi_buf_set rx = {.buffers = rx_bufs, .count = 2};
        int rc = spi_transceive_dt(&cfg->spi, &tx, &rx);
        atomic_set(&id_rc, rc);
        atomic_set(&product_id, value);
    }
    if (data->ready && atomic_get(&poll_enabled)) {
        /* Request the driver's own motion-read work even without a GPIO IRQ.
         * Its existing handler still rearms interrupts. This supplements IRQ
         * reads; it does not disable or electrically test the MOTION signal.
         */
        int rc = k_work_submit(&data->trigger_work);
        atomic_set(&poll_submit_rc, rc);
        if (rc >= 0) {
            atomic_inc(&poll_requests);
        }
    }
    k_work_reschedule(&probe_work, K_MSEC(20));
}

static void probe_thread(void *a, void *b, void *c) {
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    const struct pixart_config *cfg = sensor->config;
    atomic_set(&motion_raw, -1);
    atomic_set(&id_rc, -999); /* Not sampled yet. */
    atomic_set(&irq_monitor_rc, -999);
    if (device_is_ready(sensor)) {
        gpio_init_callback(&irq_monitor, count_irq, BIT(cfg->irq_gpio.pin));
        atomic_set(&irq_monitor_rc, gpio_add_callback(cfg->irq_gpio.port, &irq_monitor));
        k_work_schedule(&probe_work, K_NO_WAIT);
    }

    int64_t opened_at = -1;
    for (;;) {
        uint32_t dtr = 0;
        if (!device_is_ready(console) || uart_line_ctrl_get(console, UART_LINE_CTRL_DTR, &dtr) || !dtr) {
            atomic_clear(&poll_enabled);
            opened_at = -1;
            k_sleep(K_MSEC(100));
            continue;
        }
        if (opened_at < 0) {
            opened_at = k_uptime_get();
            printk("\nCHARYBDIS DIAG2: 10 seconds IRQ, then POLL. Move ball throughout.\n");
        }
        int elapsed = (int)((k_uptime_get() - opened_at) / 1000);
        bool polling = elapsed >= 10;
        atomic_set(&poll_enabled, polling);
        printk("DIAG2 t=%d mode=%s device=%d ready=%d step=%d init_err=%d id_rc=%d id=0x%02x\n",
               elapsed, polling ? "POLL" : "IRQ", device_is_ready(sensor),
               (int)atomic_get(&sensor_ready), (int)atomic_get(&init_step),
               (int)atomic_get(&init_error), (int)atomic_get(&id_rc), (unsigned)atomic_get(&product_id));
        printk("DIAG2 work=%d motion_raw=%d irq=%d irq_monitor=%d polls=%d submit=%d events=%d last_xy=%d,%d\n",
               (int)atomic_get(&work_ticks), (int)atomic_get(&motion_raw), (int)atomic_get(&irq_count),
               (int)atomic_get(&irq_monitor_rc), (int)atomic_get(&poll_requests),
               (int)atomic_get(&poll_submit_rc), (int)atomic_get(&input_events),
               (int)atomic_get(&last_x), (int)atomic_get(&last_y));
        k_sleep(K_SECONDS(1));
    }
}

/* Dedicated thread: status can continue if the sensor's workqueue stops. */
K_THREAD_DEFINE(charybdis_probe_thread, 1536, probe_thread, NULL, NULL, NULL, 10, 0, 2000);
