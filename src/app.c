#include "app.h"

#include "controls.h"
#include "player.h"
#include "songs.h"
#include "sys.h"

static int selected; /* index in the playlist */

static void select_song(int step)
{
  if (player_active()) {
    log_printf("a song is playing: stop it first (R3 + D-pad down)");
    return;
  }
  if (!songs_reload())
    return;
  int count = songs_count();
  selected = ((selected + step) % count + count) % count;
  log_printf("song %d of %d: %s", selected + 1, count, songs_name(selected));
}

static void play_selected(void)
{
  if (player_active())
    player_stop("restarted");
  if (!songs_reload())
    return;
  if (selected >= songs_count())
    selected = 0;
  const song_t *song = songs_load(selected);
  if (song)
    player_start(song);
}

void app_frame(uint32_t held)
{
  player_frame();
  switch (controls_frame(held)) {
    case CONTROL_NEXT: select_song(1); break;
    case CONTROL_PREVIOUS: select_song(-1); break;
    case CONTROL_PLAY: play_selected(); break;
    case CONTROL_STOP: player_stop("R3 + D-pad down"); break;
    case CONTROL_NONE: break;
  }
}

void app_edit_state(npad_state_t *state)
{
  if (player_active())
    player_apply(state);
  else
    state->buttons &= ~(uint64_t)controls_hidden((uint32_t)state->buttons);
}
