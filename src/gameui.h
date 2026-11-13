/* The song list in the game's own style: its UI font (Clarimo UD PE), its UI shader, and the dark box,
 * gold title and light selection band its menus have, drawn on the GPU by gpuui.c. The font and the shader
 * are read from the game's RomFS when the list is first wanted; nothing of them ships with this module.
 * The layout follows sloperinaGZ's menu in its game style (src/ootgz/nativeui.c, GPL-3; master
 * 8c3a940636). */
#ifndef GAMEUI_H
#define GAMEUI_H

#include <stdbool.h>

#include "nvn.h"
#include "overlay.h"

/* Game thread, once (later calls do nothing): reads the game's font and shader. Takes a moment, and some
 * of the game's heap, so it's left until a song list is first wanted. */
void gameui_load(void);
/* Render thread: whether the list can be drawn in the game's style now (the first time after a successful
 * gameui_load, sets up the GPU side). False: draw the plain panel. */
bool gameui_usable(void);
/* Records the list into `cmd` (a slot's, slots.h); false if there is nothing to draw. */
bool gameui_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info, nvn_rect_t area,
                   const overlay_panel_t *panel);

#endif
