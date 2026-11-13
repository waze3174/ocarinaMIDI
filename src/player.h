/* Plays a song by the clock: at each game frame, the song's input that has come due (one event at
 * most, skipping events too late to give), given to the game in place of the controller's. */
#ifndef PLAYER_H
#define PLAYER_H

#include <stdbool.h>
#include <stdint.h>

#include "npad.h"
#include "song.h"

void player_start(const song_t *song);
void player_stop(const char *reason);
bool player_active(void);
/* How far into the song playback is (0 when stopped). */
uint64_t player_elapsed_ms(void);
/* A game frame has started: move on to the input due by now, or stop after the song's end. */
void player_frame(void);
/* Replace a controller state the game is reading with the song's input for this frame. */
void player_apply(npad_state_t *state);

#endif
