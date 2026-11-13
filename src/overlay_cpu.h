/* The song list's plain panel (overlay_cpu.c): the 8x8 pixel font, rasterised on the CPU. The fallback for
 * the game's own style (gameui.h). */
#ifndef OVERLAY_CPU_H
#define OVERLAY_CPU_H

#include <stdbool.h>

#include "nvn.h"
#include "overlay.h"

/* Render thread: whether the plain panel can draw on this picture (sets itself up the first time). */
bool overlay_cpu_usable(const nvn_texture_info_t *info);
/* Records the panel's copy into `cmd` (a slot's, slots.h); false if it doesn't fit the picture. */
bool overlay_cpu_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                        nvn_rect_t area, const overlay_panel_t *panel);

#endif
