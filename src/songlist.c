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
#define SELECTED_MARKER    "> "
#define OTHER_MARKER       "  "
#define NAME_COLS          (OVERLAY_COLS - (int)(sizeof(SELECTED_MARKER) - 1))

enum { ROW_HEADING, ROW_PREVIOUS, ROW_SELECTED, ROW_NEXT };
_Static_assert(ROW_NEXT < OVERLAY_ROWS, "the list's rows");

static uint64_t shown_until_ms;

void songlist_linger(void)
{
  shown_until_ms = sys_ms() + LINGER_MS;
}

/* As the font can draw it: '_' (the converter's word separator) as a space, anything else outside
 * ASCII as '?'. */
static char shown_char(char c)
{
  if (c == '_')
    return ' ';
  return c >= ' ' && c <= '~' ? c : '?';
}

/* A playlist entry as shown: without ".oca", cut to NAME_COLS with "...". */
static void display_name(char out[NAME_COLS + 1], const char *file_name)
{
  size_t len = strlen(file_name);
  size_t suffix_len = sizeof(SONG_SUFFIX) - 1;
  if (len >= suffix_len && !memcmp(file_name + len - suffix_len, SONG_SUFFIX, suffix_len))
    len -= suffix_len;
  bool cut = len > NAME_COLS;
  size_t kept = cut ? NAME_COLS - (sizeof(ELLIPSIS) - 1) : len;
  for (size_t i = 0; i < kept; i++)
    out[i] = shown_char(file_name[i]);
  if (cut)
    memcpy(out + kept, ELLIPSIS, sizeof(ELLIPSIS) - 1);
  out[cut ? NAME_COLS : kept] = 0;
}

static void song_row(char *row, const char *marker, int index)
{
  char name[NAME_COLS + 1];
  display_name(name, songs_name(index));
  snprintf(row, OVERLAY_COLS + 1, "%s%s", marker, name);
}

/* "song 3 of 12" on the left, "playing 1:05" or "stopped" on the right. */
static void heading_row(char *row, int selected, int count)
{
  char where[OVERLAY_COLS + 1], state[OVERLAY_COLS + 1];
  if (count)
    snprintf(where, sizeof(where), "song %d of %d", selected + 1, count);
  else
    snprintf(where, sizeof(where), "ocarinaMIDI");
  if (player_active()) {
    unsigned seconds = (unsigned)(player_elapsed_ms() / MS_PER_SECOND);
    snprintf(state, sizeof(state), "playing %u:%02u", seconds / SECONDS_PER_MINUTE, seconds % SECONDS_PER_MINUTE);
  } else {
    snprintf(state, sizeof(state), "stopped");
  }
  snprintf(row, OVERLAY_COLS + 1, "%-*s%s", OVERLAY_COLS - (int)strlen(state), where, state);
}

static void fill(overlay_panel_t *panel, int selected)
{
  int count = songs_count();
  panel->style[ROW_HEADING] = OVERLAY_HEADING;
  panel->style[ROW_PREVIOUS] = OVERLAY_DIM;
  panel->style[ROW_SELECTED] = OVERLAY_TEXT;
  panel->style[ROW_NEXT] = OVERLAY_DIM;
  heading_row(panel->text[ROW_HEADING], selected, count);
  if (!count) {
    snprintf(panel->text[ROW_SELECTED], OVERLAY_COLS + 1, OTHER_MARKER "no songs in playlist.txt");
    return;
  }
  song_row(panel->text[ROW_SELECTED], SELECTED_MARKER, selected);
  if (count > 2) /* with two, the previous song is also the next */
    song_row(panel->text[ROW_PREVIOUS], OTHER_MARKER, songs_step(selected, -1));
  if (count > 1)
    song_row(panel->text[ROW_NEXT], OTHER_MARKER, songs_step(selected, 1));
}

void songlist_frame(bool menu_open, int selected)
{
  overlay_panel_t panel;
  memset(&panel, 0, sizeof(panel));
  panel.shown = menu_open || sys_ms() < shown_until_ms;
  if (panel.shown)
    fill(&panel, selected);
  overlay_publish(&panel);
}
