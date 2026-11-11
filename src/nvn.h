/* The game's NVN. main fetches every NVN function by name, through nvnBootstrapLoader and the
 * nvnDeviceGetProcAddress it returns, so wrapping the loader in main's GOT shows us the device, the
 * swapchain textures and each present. Types and hooks adapted from sloperinaGZ's src/ootgz/nvn.c and
 * nvnapi.h (GPL-3); signatures and enum values are NVN 1's, which this game still uses. */
#ifndef NVN_H
#define NVN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct nvn_device nvn_device_t;
typedef struct nvn_queue nvn_queue_t;
typedef struct nvn_window nvn_window_t;
typedef struct nvn_texture nvn_texture_t;
typedef uint64_t nvn_addr_t;
typedef uint64_t nvn_handle_t;
typedef struct { int32_t x, y, z, w, h, d; } nvn_region_t;
typedef struct { int32_t x, y, w, h; } nvn_rect_t;

/* Room for an NVN object we own: NVN 1's are at most 0x100 bytes, NVN 2's may have grown. */
#define NVN_OBJ_STORAGE 0x400
typedef struct { _Alignas(16) uint8_t b[NVN_OBJ_STORAGE]; } nvn_obj_t;

/* At module init: wrap main's nvnBootstrapLoader. NULL, or why it can't. */
const char *nvn_hook_game(uintptr_t main_base);
/* The game's device, once it has made one (NULL before). */
nvn_device_t *nvn_device(void);
/* An NVN function by name, through the game's device (NULL before it has one). */
void *nvn_proc(const char *name);

/* Called before each of the game's presents, with the texture it presents (overlay.c). */
void overlay_before_present(nvn_queue_t *queue, nvn_window_t *window, nvn_texture_t *texture);

#endif
