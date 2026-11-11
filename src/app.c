#include "app.h"

#include "controls.h"
#include "player.h"
#include "songlist.h"
#include "songs.h"
#include "sys.h"

static int selected; /* index in the playlist */
static bool menu_was_open;

static void reload_playlist(void)
{
  songs_reload();
  if (selected >= songs_count())
    selected = 0;
}

static void select_song(int step)
{
  if (player_active()) {
    log_printf("a song is playing: stop it first (R3 + D-pad down)");
    return;
  }
  if (!songs_count())
    return;
  selected = songs_step(selected, step);
  log_printf("song %d of %d: %s", selected + 1, songs_count(), songs_name(selected));
}

static void play_selected(void)
{
  if (player_active())
    player_stop("restarted");
  const song_t *song = songs_count() ? songs_load(selected) : 0;
  if (song)
    player_start(song);
}

static void run(control_t command)
{
  switch (command) {
    case CONTROL_NEXT: select_song(1); break;
    case CONTROL_PREVIOUS: select_song(-1); break;
    case CONTROL_PLAY: play_selected(); break;
    case CONTROL_STOP: player_stop("R3 + D-pad down"); break;
    case CONTROL_NONE: return;
  }
  songlist_linger();
}

void app_frame(uint32_t held)
{
  player_frame();
  bool menu_open = controls_menu_open(held);
  /* The list on screen is the one on the SD card now. Not while a song plays: reading the card on
   * the game's thread could hold up a frame. */
  if (menu_open && !menu_was_open && !player_active())
    reload_playlist();
  menu_was_open = menu_open;
  run(controls_frame(held));
  songlist_frame(menu_open, selected);
}

void app_edit_state(npad_state_t *state)
{
  if (player_active())
    player_apply(state);
  else
    state->buttons &= ~(uint64_t)controls_hidden((uint32_t)state->buttons);
}
