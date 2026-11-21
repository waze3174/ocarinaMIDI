/* The song list's plain panel (overlay_cpu.c): the 8x8 pixel font, rasterised on the CPU. The fallback for
 * the game's own style (gameui.h). */
#ifndef OVERLAY_CPU_H
#define OVERLAY_CPU_H

#include <stdbool.h>

#include "nvn.h"
#include "overlay.h"
#include "sys.h"

/* Render thread: takes the panel's pixel buffers, sized for this picture. Not OK: the reason is logged;
 * INIT_NO_MEMORY leaves nothing taken, and a later call tries again. */
init_result_t overlay_cpu_init(const nvn_texture_info_t *info);
/* Render thread: whether the plain panel can draw on this picture (after overlay_cpu_init returned OK). */
bool overlay_cpu_usable(const nvn_texture_info_t *info);
/* Records the panel's copy into `cmd` (a slot's, slots.h); false if it doesn't fit the picture. */
bool overlay_cpu_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                        nvn_rect_t area, const overlay_panel_t *panel);

#endif
