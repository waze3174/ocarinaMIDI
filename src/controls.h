/* The add-on's controls: hold the right stick in (R3) and press the D-pad. Chosen to stay clear of
 * sloperinaGZ (R + ..., L3, frame advance on L or R) and of the ocarina's own buttons. */
#ifndef CONTROLS_H
#define CONTROLS_H

#include <stdbool.h>
#include <stdint.h>

typedef enum { CONTROL_NONE, CONTROL_NEXT, CONTROL_PREVIOUS, CONTROL_PLAY, CONTROL_STOP } control_t;

/* The command pressed this frame, from every button held on any controller during it. */
control_t controls_frame(uint32_t held);
/* True while R3 is held: the controls are in use. */
bool controls_menu_open(uint32_t held);
/* Buttons to hide from the game in a state with these buttons (the D-pad while R3 is held). */
uint32_t controls_hidden(uint32_t buttons);

#endif
