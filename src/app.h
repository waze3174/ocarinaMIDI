/* What the add-on does with each game frame and each controller state the game reads. */
#ifndef APP_H
#define APP_H

#include <stdint.h>

#include "npad.h"

/* A game frame ended; `held` is every button held on a connected controller during it. */
void app_frame(uint32_t held);
/* A controller state the game is about to see (connected ones only). */
void app_edit_state(npad_state_t *state);

#endif
