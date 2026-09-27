/* Read-only companion channel. No key presses or host commands are collected.
 * This separate CDC interface allows Studio and the overlay to coexist.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/printk.h>
#include <zmk/keymap.h>
#include <zmk/behavior.h>
#include <zmk/matrix.h>
#include <zmk/hid.h>
#include <zmk/usb.h>
#include <zmk/physical_layouts.h>
#include <string.h>
#include <stdarg.h>

static const struct device *const uart = DEVICE_DT_GET(DT_NODELABEL(charybdis_overlay_uart));
static bool connected(void) {
    uint32_t dtr = 0;
    return zmk_usb_get_status() != USB_DC_SUSPEND &&
           zmk_usb_get_conn_state() == ZMK_USB_CONN_HID &&
           uart_line_ctrl_get(uart, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
}
static bool send(const char *s) {
    if (!connected()) return false;
    while (*s) { if (!connected()) return false; uart_poll_out(uart, *s++); }
    return true;
}
static bool fmt(const char *f, ...) {
    char b[192]; va_list a; va_start(a, f);
    int n = vsnprintk(b, sizeof(b), f, a); va_end(a);
    return n >= 0 && n < sizeof(b) && send(b);
}
static bool quoted(const char *s) {
    if (!send("\"")) return false;
    if (s) for (; *s; s++) {
        unsigned char ch = *s;
        if (ch == '"' || ch == '\\') { char b[]={'\\', ch, 0}; if (!send(b)) return false; }
        else if (ch < 32) { if (!fmt("\\u%04x", ch)) return false; }
        else { char b[]={ch, 0}; if (!send(b)) return false; }
    }
    return send("\"");
}
static uint32_t hash_bytes(uint32_t h, const void *p, size_t n) {
    const unsigned char *s=p;
    while(n--) h=(h^*s++)*16777619u;
    return h;
}
static uint32_t map_hash(void) {
    uint32_t h=2166136261u;
    for(int i=0;i<ZMK_KEYMAP_LAYERS_LEN;i++) {
        uint8_t id=zmk_keymap_layer_index_to_id(i); if(id==UINT8_MAX) break;
        h=hash_bytes(h,&id,sizeof(id));
        const char *name=zmk_keymap_layer_name(id);
        if(name) h=hash_bytes(h,name,strlen(name)+1);
        for(int j=0;j<ZMK_KEYMAP_LEN;j++) {
            const struct zmk_behavior_binding *b=zmk_keymap_get_layer_binding_at_idx(id,j);
            if(!b) continue;
            if(b->behavior_dev) h=hash_bytes(h,b->behavior_dev,strlen(b->behavior_dev)+1);
            h=hash_bytes(h,&b->param1,sizeof(b->param1)); h=hash_bytes(h,&b->param2,sizeof(b->param2));
        }
    }
    int selected=zmk_physical_layouts_get_selected();
    return hash_bytes(h,&selected,sizeof(selected));
}
static bool snapshot(uint32_t revision) {
    const struct zmk_physical_layout *const *layouts;
    size_t count=zmk_physical_layouts_get_list(&layouts);
    int selected=zmk_physical_layouts_get_selected();
    if(selected<0 || selected>=count) return false;
    const struct zmk_physical_layout *layout=layouts[selected];
    if(!fmt("\n{\"type\":\"begin\",\"protocol\":1,\"revision\":%u,\"keys\":[",revision)) return false;
    for(size_t i=0;i<layout->keys_len;i++) {
        const struct zmk_key_physical_attrs *k=&layout->keys[i];
        if(!fmt("%s[%d,%d,%d,%d]",i?",":"",k->x,k->y,k->width,k->height)) return false;
    }
    if(!send("]}\n")) return false;
    for(int i=0;i<ZMK_KEYMAP_LAYERS_LEN;i++) {
        uint8_t id=zmk_keymap_layer_index_to_id(i); if(id==UINT8_MAX) break;
        if(!fmt("{\"type\":\"layer\",\"id\":%u,\"name\":",id) || !quoted(zmk_keymap_layer_name(id)) || !send(",\"bindings\":[")) return false;
        for(int j=0;j<ZMK_KEYMAP_LEN;j++) {
            const struct zmk_behavior_binding *b=zmk_keymap_get_layer_binding_at_idx(id,j);
            if(!send(j?",[":"[") || !quoted(b?b->behavior_dev:NULL) ||
               !fmt(",%u,%u]",b?b->param1:0,b?b->param2:0)) return false;
        }
        if(!send("]}\n")) return false;
    }
    /* Reject snapshots if Studio changed the map during transmission. */
    return fmt("{\"type\":\"end\",\"revision\":%u,\"valid\":%s}\n",revision,map_hash()==revision?"true":"false");
}
static void overlay_main(void *a, void *b, void *c) {
    if(!device_is_ready(uart)) return;
    bool was=false; uint32_t prior_hash=0,prior_state=0; uint8_t prior_mods=0;
    int64_t last_map=0,last_state=0;
    for(;;) {
        k_sleep(K_MSEC(25));
        if(!connected()) { was=false; continue; }
        int64_t now=k_uptime_get();
        if(!was || now-last_map>=1000) {
            uint32_t h=map_hash();
            if(!was || h!=prior_hash) { if(!snapshot(h)) { was=false;continue; } prior_hash=h; }
            last_map=now;
        }
        uint32_t state=zmk_keymap_layer_state() | BIT(zmk_keymap_layer_default());
        uint8_t mods=zmk_hid_get_keyboard_report()->body.modifiers;
        if(!was || state!=prior_state || mods!=prior_mods || now-last_state>=1000) {
            if(!fmt("{\"type\":\"state\",\"layers\":%u,\"mods\":%u,\"default\":%u}\n",state,mods,zmk_keymap_layer_default())) {was=false;continue;}
            prior_state=state;prior_mods=mods;last_state=now;
        }
        was=true;
    }
}
K_THREAD_DEFINE(charybdis_overlay_thread, 2048, overlay_main, NULL, NULL, NULL, 10, 0, 1000);
