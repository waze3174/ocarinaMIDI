#include "player.h"

#include "sys.h"

#define MS_PER_SECOND 1000
/* A wait between two game frames longer than this (loading, a hitch) pauses the song: it carries on
 * where it was instead of hurrying through the notes it missed. */
#define STALL_MS 250
#define SECONDS_ARGS(ms) (unsigned)((ms) / MS_PER_SECOND), (unsigned)((ms) % MS_PER_SECOND) /* for "%u.%03u" */

static const song_t *song;
static uint32_t next_event;
static song_event_t current; /* the input the game gets this frame */
static uint64_t song_start_ms; /* the clock at the song's time 0, moved on by each stall */
static uint64_t started_ms, last_frame_ms;
static uint64_t max_late_ms, stalled_ms;
static uint32_t frames, stalls, states_edited;

static uint64_t tick_ms(uint32_t tick)
{
  return (uint64_t)tick * MS_PER_SECOND / song->header->ticks_per_second;
}

static uint64_t length_ms(void)
{
  return tick_ms(song->header->total_ticks);
}

static bool events_left(void)
{
  return next_event < song->header->event_count;
}

/* One event at most per game frame, so the game sees each press and each release for a frame at
 * least. Events that come due faster than the game's frames are given late, in order. */
static void take_due_event(uint64_t song_ms)
{
  if (!events_left())
    return;
  uint64_t due_ms = tick_ms(song->events[next_event].tick);
  if (due_ms > song_ms)
    return;
  if (song_ms - due_ms > max_late_ms)
    max_late_ms = song_ms - due_ms;
  current = song->events[next_event++];
}

static uint32_t stick_direction_bits(int32_t x, int32_t y, uint32_t left, uint32_t up, uint32_t right, uint32_t down)
{
  return (x < -NPAD_STICK_DIRECTION_THRESHOLD ? left : 0) | (x > NPAD_STICK_DIRECTION_THRESHOLD ? right : 0) |
         (y > NPAD_STICK_DIRECTION_THRESHOLD ? up : 0) | (y < -NPAD_STICK_DIRECTION_THRESHOLD ? down : 0);
}

void player_start(const song_t *new_song)
{
  song = new_song;
  next_event = 0;
  current = (song_event_t){ 0 };
  started_ms = last_frame_ms = song_start_ms = sys_ms();
  max_late_ms = stalled_ms = 0;
  frames = stalls = states_edited = 0;
  take_due_event(0);
  log_printf("playing \"%s\": %u events over %u.%03u s (%u ticks per second)", song->header->title,
             (unsigned)song->header->event_count, SECONDS_ARGS(length_ms()), (unsigned)song->header->ticks_per_second);
}

void player_stop(const char *reason)
{
  if (!song)
    return;
  uint64_t now = sys_ms();
  uint64_t played_ms = now - started_ms;
  unsigned fps_tenths = played_ms ? (unsigned)((uint64_t)frames * 10 * MS_PER_SECOND / played_ms) : 0;
  unsigned edits_per_frame_tenths = frames ? (unsigned)((uint64_t)states_edited * 10 / frames) : 0;
  log_printf("stopped (%s) at %u.%03u s of %u.%03u s, after %u.%03u s: %u frames, %u.%u per second", reason,
             SECONDS_ARGS(now - song_start_ms), SECONDS_ARGS(length_ms()), SECONDS_ARGS(played_ms), (unsigned)frames,
             fps_tenths / 10, fps_tenths % 10);
  log_printf("timing: events up to %u ms late; %u stalls paused it for %u ms; %u.%u controller states edited per frame",
             (unsigned)max_late_ms, (unsigned)stalls, (unsigned)stalled_ms, edits_per_frame_tenths / 10,
             edits_per_frame_tenths % 10);
  song = 0;
}

bool player_active(void)
{
  return song != 0;
}

uint64_t player_elapsed_ms(void)
{
  return song ? sys_ms() - song_start_ms : 0;
}

void player_frame(void)
{
  if (!song)
    return;
  uint64_t now = sys_ms();
  uint64_t gap = now - last_frame_ms;
  last_frame_ms = now;
  if (gap > STALL_MS) {
    song_start_ms += gap;
    stalled_ms += gap;
    stalls++;
  }
  frames++;
  uint64_t song_ms = now - song_start_ms;
  /* checked before taking an event, so the last one (a release) is also seen for a frame */
  if (!events_left() && song_ms >= length_ms()) {
    player_stop("end of the song");
    return;
  }
  take_due_event(song_ms);
}

void player_apply(npad_state_t *state)
{
  state->buttons = current.buttons |
                   stick_direction_bits(current.lx, current.ly, BTN_LS_LEFT, BTN_LS_UP, BTN_LS_RIGHT, BTN_LS_DOWN) |
                   stick_direction_bits(current.rx, current.ry, BTN_RS_LEFT, BTN_RS_UP, BTN_RS_RIGHT, BTN_RS_DOWN);
  state->lx = current.lx;
  state->ly = current.ly;
  state->rx = current.rx;
  state->ry = current.ry;
  states_edited++;
}
