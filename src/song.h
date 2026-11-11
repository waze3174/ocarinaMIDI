/* The song files tools/midi2oca.py writes (docs/FORMAT.md): a header, then the controller input
 * to give the game, as events sorted by time. Little endian. */
#ifndef SONG_H
#define SONG_H

#include <stdint.h>

#define SONG_MAGIC     0x3141434Fu /* "OCA1" */
#define SONG_VERSION   1
#define SONG_TITLE_LEN 48

typedef struct {
  uint32_t magic;
  uint16_t version;
  uint16_t ticks_per_second; /* the events' time unit */
  uint32_t event_count;
  uint32_t total_ticks;      /* the song's length */
  char     title[SONG_TITLE_LEN];
} song_header_t;

typedef struct {
  uint32_t tick;    /* from this time on (0 = when playback starts) */
  uint32_t buttons; /* nn::hid::NpadButton bits */
  int16_t  lx, ly, rx, ry;
} song_event_t;

_Static_assert(sizeof(song_header_t) == 64, "song header layout");
_Static_assert(sizeof(song_event_t) == 16, "song event layout");

typedef struct {
  const song_header_t *header;
  const song_event_t  *events;
} song_t;

#endif
