/* One text panel at the top centre of the game's picture (overlay.c draws it before each present). */
#ifndef OVERLAY_H
#define OVERLAY_H

#include <stdbool.h>
#include <stdint.h>

#define OVERLAY_ROWS 4
#define OVERLAY_COLS 40

typedef enum { OVERLAY_TEXT, OVERLAY_DIM, OVERLAY_HEADING, OVERLAY_STYLES } overlay_style_t;

typedef struct {
  bool shown;
  uint8_t style[OVERLAY_ROWS]; /* overlay_style_t */
  char text[OVERLAY_ROWS][OVERLAY_COLS + 1]; /* ASCII, NUL padded */
} overlay_panel_t;

/* What the panel shows from now on (copied; from any one thread). */
void overlay_publish(const overlay_panel_t *panel);

#endif
