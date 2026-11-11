/* Plays a song: one step per game frame, giving the game the song's buttons and sticks meanwhile. */
#ifndef PLAYER_H
#define PLAYER_H

#include <stdbool.h>

#include "npad.h"
#include "song.h"

void player_start(const song_t *song);
void player_stop(const char *reason);
bool player_active(void);
/* A game frame has passed: move on to its input, or stop after the last frame. */
void player_frame(void);
/* Replace a controller state the game is reading with the song's input for this frame. */
void player_apply(npad_state_t *state);

#endif
