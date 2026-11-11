#include "controls.h"

#include "npad.h"

#define CONTROL_MODIFIER BTN_RSTICK

static uint32_t held_last_frame;

control_t controls_frame(uint32_t held)
{
  uint32_t pressed = held & ~held_last_frame;
  held_last_frame = held;
  if (!controls_menu_open(held))
    return CONTROL_NONE;
  if (pressed & BTN_DRIGHT)
    return CONTROL_NEXT;
  if (pressed & BTN_DLEFT)
    return CONTROL_PREVIOUS;
  if (pressed & BTN_DUP)
    return CONTROL_PLAY;
  if (pressed & BTN_DDOWN)
    return CONTROL_STOP;
  return CONTROL_NONE;
}

bool controls_menu_open(uint32_t held)
{
  return held & CONTROL_MODIFIER;
}

uint32_t controls_hidden(uint32_t buttons)
{
  return controls_menu_open(buttons) ? BTN_DPAD : 0;
}
