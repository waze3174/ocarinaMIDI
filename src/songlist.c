#include "songlist.h"

#include "overlay.h"
#include "player.h"
#include "songs.h"
#include "sys.h"

#define LINGER_MS          3000
#define MS_PER_SECOND      1000
#define SECONDS_PER_MINUTE 60
#define SONG_SUFFIX        ".oca"
#define ELLIPSIS           "..."

enum { LINE_PREVIOUS, LINE_SELECTED, LINE_NEXT };
_Static_assert(LINE_NEXT < OVERLAY_LINES, "the list's lines");

static uint64_t shown_until_ms;

void songlist_linger(void)
{
  shown_until_ms = sys_ms() + LINGER_MS;
}

void songlist_hide(void)
{
  shown_until_ms = 0;
}

/* As the font can draw it: '_' (the converter's word separator) as a space, anything else outside
 * ASCII as '?'. */
static char shown_char(char c)
{
  if (c == '_')
    return ' ';
  return c >= ' ' && c <= '~' ? c : '?';
}

/* A playlist entry as shown: without ".oca", cut to OVERLAY_NAME_COLS with "...". */
static void display_name(char out[OVERLAY_NAME_COLS + 1], const char *file_name)
{
  size_t len = strlen(file_name);
  size_t suffix_len = sizeof(SONG_SUFFIX) - 1;
  if (len >= suffix_len && !memcmp(file_name + len - suffix_len, SONG_SUFFIX, suffix_len))
    len -= suffix_len;
  bool cut = len > OVERLAY_NAME_COLS;
  size_t kept = cut ? OVERLAY_NAME_COLS - (sizeof(ELLIPSIS) - 1) : len;
  for (size_t i = 0; i < kept; i++)
    out[i] = shown_char(file_name[i]);
  if (cut)
    memcpy(out + kept, ELLIPSIS, sizeof(ELLIPSIS) - 1);
  out[cut ? OVERLAY_NAME_COLS : kept] = 0;
}

static void song_line(overlay_panel_t *panel, int line, int index)
{
  char name[OVERLAY_NAME_COLS + 1];
  display_name(name, songs_name(index));
  snprintf(panel->line[line], sizeof(panel->line[line]), "%s", name);
}

static void fill_place(overlay_panel_t *panel, int selected, int count)
{
  if (count)
    snprintf(panel->where, sizeof(panel->where), "song %d of %d", selected + 1, count);
  else
    snprintf(panel->where, sizeof(panel->where), "ocarinaMIDI");
}

/* "playing 1:05" or "stopped" */
static void fill_state(overlay_panel_t *panel)
{
  if (player_active()) {
    unsigned seconds = (unsigned)(player_elapsed_ms() / MS_PER_SECOND);
    snprintf(panel->state, sizeof(panel->state), "playing %u:%02u", seconds / SECONDS_PER_MINUTE,
             seconds % SECONDS_PER_MINUTE);
  } else {
    snprintf(panel->state, sizeof(panel->state), "stopped");
  }
}

static void fill(overlay_panel_t *panel, int selected)
{
  int count = songs_count();
  fill_place(panel, selected, count);
  fill_state(panel);
  if (!count) {
    snprintf(panel->line[LINE_SELECTED], sizeof(panel->line[LINE_SELECTED]), "no songs in playlist.txt");
    panel->selected = OVERLAY_NO_SELECTION;
    return;
  }
  panel->selected = LINE_SELECTED;
  song_line(panel, LINE_SELECTED, selected);
  if (count > 2) /* with two, the previous song is also the next */
    song_line(panel, LINE_PREVIOUS, songs_step(selected, -1));
  if (count > 1)
    song_line(panel, LINE_NEXT, songs_step(selected, 1));
}

void songlist_frame(int selected)
{
  overlay_panel_t panel;
  memset(&panel, 0, sizeof(panel));
  panel.selected = OVERLAY_NO_SELECTION;
  panel.shown = sys_ms() < shown_until_ms;
  if (panel.shown)
    fill(&panel, selected);
  overlay_publish(&panel);
}
