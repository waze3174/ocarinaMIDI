#include "player.h"

#include "sys.h"

static const song_t *song;
static uint32_t frame;      /* of playback: 0 is the frame it started in */
static uint32_t next_event;
static song_event_t current; /* the input the game gets this frame */
static uint64_t start_ms;
static uint32_t states_edited;

static void take_due_events(void)
{
  while (next_event < song->header->event_count && song->events[next_event].frame <= frame)
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
  frame = 0;
  next_event = 0;
  current = (song_event_t){ 0 };
  start_ms = sys_ms();
  states_edited = 0;
  take_due_events();
  log_printf("playing \"%s\": %u events over %u frames (made for %u fps)", song->header->title,
             (unsigned)song->header->event_count, (unsigned)song->header->total_frames, (unsigned)song->header->fps);
}

void player_stop(const char *reason)
{
  if (!song)
    return;
  uint64_t ms = sys_ms() - start_ms;
  unsigned fps_tenths = ms ? (unsigned)((uint64_t)frame * 10000 / ms) : 0;
  unsigned edits_per_frame_tenths = frame ? (unsigned)((uint64_t)states_edited * 10 / frame) : 0;
  log_printf("stopped (%s) after %u frames in %u.%03u s: %u.%u frames per second (song made for %u); "
             "%u.%u controller states edited per frame",
             reason, (unsigned)frame, (unsigned)(ms / 1000), (unsigned)(ms % 1000), fps_tenths / 10, fps_tenths % 10,
             (unsigned)song->header->fps, edits_per_frame_tenths / 10, edits_per_frame_tenths % 10);
  song = 0;
}

bool player_active(void)
{
  return song != 0;
}

void player_frame(void)
{
  if (!song)
    return;
  frame++;
  if (frame >= song->header->total_frames) {
    player_stop("end of the song");
    return;
  }
  take_due_events();
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
