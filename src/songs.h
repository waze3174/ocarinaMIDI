/* The songs on the SD card: SONGS_DIR/playlist.txt lists the .oca files, one per line. */
#ifndef SONGS_H
#define SONGS_H

#include <stdbool.h>

#include "song.h"

/* Mounts the SD card if needed and reads the playlist again; false (logged) if it's missing or empty. */
bool songs_reload(void);
int songs_count(void);
const char *songs_name(int index);
/* Reads and checks one song; it stays valid until the next songs_load. NULL (logged) on error. */
const song_t *songs_load(int index);

#endif
