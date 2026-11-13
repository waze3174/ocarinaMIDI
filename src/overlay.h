/* The song list on screen: one panel at the top centre of the game's picture. songlist.c says what it
 * holds; gameui.c draws it in the game's own style (fonts, shader, colours loaded from the game's files)
 * and overlay_cpu.c in a plain pixel font when those aren't there. overlay.c picks the one to use before
 * each present. */
#ifndef OVERLAY_H
#define OVERLAY_H

#include <stdbool.h>
#include <stdint.h>

#define OVERLAY_COLS      40
#define OVERLAY_MARKER_COLS 2 /* the plain panel's "> " before a song: names are cut to fit what's left */
#define OVERLAY_NAME_COLS (OVERLAY_COLS - OVERLAY_MARKER_COLS)
#define OVERLAY_LINES     3 /* the songs shown: before the selected one, it, and after it */
#define OVERLAY_NO_SELECTION (-1)

typedef struct {
  bool shown;
  char where[OVERLAY_COLS + 1];                /* "song 3 of 12", or the module's name with no songs */
  char state[OVERLAY_COLS + 1];                /* "playing 1:05", "stopped" */
  char line[OVERLAY_LINES][OVERLAY_COLS + 1];  /* ASCII, "" for a line with nothing */
  int8_t selected;                             /* the line of the selected song, or OVERLAY_NO_SELECTION */
} overlay_panel_t;

/* What the panel shows from now on (copied; from any one thread). */
void overlay_publish(const overlay_panel_t *panel);

#endif
