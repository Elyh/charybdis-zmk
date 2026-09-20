/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdint.h>

struct orientation_fraction {
    int64_t x;
    int64_t y;
};

/* Right produces (+x,-y); towards the user produces (-x,-y).
 * x' = (x-y)/sqrt(2), y' = (-x-y)/sqrt(2).
 * Retain fractional counts across frames for slow, precise movement.
 */
static inline void orientation_map(struct orientation_fraction *fraction,
                                   int64_t x, int64_t y, int32_t *out_x, int32_t *out_y) {
    int64_t scaled_x = (x - y) * 46341 + fraction->x;
    int64_t scaled_y = (-x - y) * 46341 + fraction->y;
    *out_x = (int32_t)(scaled_x / 65536);
    *out_y = (int32_t)(scaled_y / 65536);
    fraction->x = scaled_x % 65536;
    fraction->y = scaled_y % 65536;
}
