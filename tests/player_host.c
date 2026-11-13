/* Runs src/player.c on the PC for tests/test_player.py: plays the song file given as the argument, with
 * game frames at the times (ms) read from stdin, one per line. Prints each frame's time and what the
 * game gets ("<ms> <buttons> <left stick x>"), then "end <ms>" once the song has stopped. The module's
 * log goes to stderr. */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "../src/player.h"

static uint64_t now_ms;

uint64_t sys_ms(void)
{
  return now_ms;
}

void log_printf(const char *fmt, ...)
{
  va_list ap;
  va_start(ap, fmt);
  vfprintf(stderr, fmt, ap);
  va_end(ap);
  fputc('\n', stderr);
}

static void *read_file(const char *path)
{
  FILE *file = fopen(path, "rb");
  if (!file)
    return 0;
  fseek(file, 0, SEEK_END);
  long size = ftell(file);
  fseek(file, 0, SEEK_SET);
  void *data = malloc((size_t)size);
  if (data && fread(data, 1, (size_t)size, file) != (size_t)size) {
    free(data);
    data = 0;
  }
  fclose(file);
  return data;
}

int main(int argc, char **argv)
{
  void *data = argc == 2 ? read_file(argv[1]) : 0;
  if (!data) {
    fprintf(stderr, "usage: player_host <song.oca> < frame times\n");
    return 2;
  }
  song_t song = { data, (const song_event_t *)((const song_header_t *)data + 1) };
  player_start(&song);
  unsigned long long frame_ms;
  while (scanf("%llu", &frame_ms) == 1) {
    now_ms = frame_ms;
    player_frame();
    if (!player_active()) {
      printf("end %llu\n", frame_ms);
      break;
    }
    npad_state_t state = { .attributes = NPAD_ATTR_CONNECTED };
    player_apply(&state);
    printf("%llu %llu %d\n", frame_ms, (unsigned long long)state.buttons, (int)state.lx);
  }
  free(data);
  return 0;
}
