/* The songs on the SD card: SONGS_DIR/playlist.txt lists the .oca files, one per line. */
#ifndef SONGS_H
#define SONGS_H

#include <stdbool.h>

#include "song.h"

/* Mounts the SD card if needed and reads the playlist again, leaving out songs whose file is missing;
 * false (logged) if no song is left. */
bool songs_reload(void);
int songs_count(void);
/* The song `step` places from `index` (negative: back), wrapping around the playlist. */
int songs_step(int index, int step);
const char *songs_name(int index);
/* Reads and checks one song; it stays valid until the next songs_load. NULL (logged) on error. */
const song_t *songs_load(int index);

#endif
