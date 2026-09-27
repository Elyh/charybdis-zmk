/* SPDX-License-Identifier: MIT */
#define DT_DRV_COMPAT zmk_charybdis_orientation

#include <zephyr/device.h>
#include <zephyr/input/input.h>
#include <zephyr/kernel.h>
#include "orientation_math.h"

struct orientation_data {
    int64_t x;
    int64_t y;
    bool motion_pending;
    struct orientation_fraction fraction;
};

static void emit_motion(const struct device *dev, bool sync) {
    struct orientation_data *data = dev->data;
    int32_t x, y;
    orientation_map(&data->fraction, data->x, data->y, &x, &y);
    data->x = 0;
    data->y = 0;
    data->motion_pending = false;
    input_report_rel(dev, INPUT_REL_X, x, false, K_NO_WAIT);
    input_report_rel(dev, INPUT_REL_Y, y, sync, K_NO_WAIT);
}

static void orientation_event(struct input_event *event, void *user_data) {
    const struct device *dev = user_data;
    struct orientation_data *data = dev->data;
    if (event->type == INPUT_EV_REL &&
        (event->code == INPUT_REL_X || event->code == INPUT_REL_Y)) {
        if (event->code == INPUT_REL_X) {
            data->x += event->value;
        } else {
            data->y += event->value;
        }
        data->motion_pending = true;
        if (event->sync) {
            emit_motion(dev, true);
        }
        return;
    }

    /* Keep other event types unchanged, including their frame boundary. */
    if (event->sync && data->motion_pending) {
        emit_motion(dev, false);
    }
    input_report(dev, event->type, event->code, event->value, event->sync, K_NO_WAIT);
}

#define ORIENTATION_DEFINE(n) \
    static struct orientation_data orientation_data_##n; \
    DEVICE_DT_INST_DEFINE(n, NULL, NULL, &orientation_data_##n, NULL, POST_KERNEL, \
                          CONFIG_INPUT_INIT_PRIORITY, NULL); \
    INPUT_CALLBACK_DEFINE(DEVICE_DT_GET(DT_INST_PHANDLE(n, device)), orientation_event, \
                          (void *)DEVICE_DT_INST_GET(n));

DT_INST_FOREACH_STATUS_OKAY(ORIENTATION_DEFINE)
