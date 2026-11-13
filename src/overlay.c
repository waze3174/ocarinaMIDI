/* Before each of the game's presents (nvn.c): draws the song list, if it's shown, in the plain panel
 * (overlay_cpu.c), as one command buffer on a slot (slots.c). The panel itself comes from the game's controller thread
 * (songlist.c). Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3). */
#include "overlay.h"

#include "nvn.h"
#include "overlay_cpu.h"
#include "slots.h"
#include "sys.h"

#define COMMAND_BYTES 0x20000 /* command memory per slot: far more than a panel's 150 quads need */

static enum { OV_NONE, OV_READY, OV_FAILED } state;

/* --- the panel, from the game's controller thread to its present thread ------------------------- */

static overlay_panel_t published;
static uint32_t published_seq; /* odd while `published` is being written */

void overlay_publish(const overlay_panel_t *panel)
{
  uint32_t seq = __atomic_load_n(&published_seq, __ATOMIC_RELAXED);
  __atomic_store_n(&published_seq, seq + 1, __ATOMIC_RELAXED);
  __atomic_thread_fence(__ATOMIC_RELEASE);
  memcpy(&published, panel, sizeof(published));
  __atomic_store_n(&published_seq, seq + 2, __ATOMIC_RELEASE);
}

/* The newest panel; the one read last time if it's being written right now. */
static const overlay_panel_t *newest_panel(void)
{
  static overlay_panel_t newest;
  overlay_panel_t attempt;
  uint32_t before = __atomic_load_n(&published_seq, __ATOMIC_ACQUIRE);
  if (before & 1)
    return &newest;
  memcpy(&attempt, &published, sizeof(attempt));
  __atomic_thread_fence(__ATOMIC_ACQUIRE);
  if (__atomic_load_n(&published_seq, __ATOMIC_RELAXED) == before)
    memcpy(&newest, &attempt, sizeof(newest));
  return &newest;
}

/* --- drawing ------------------------------------------------------------------------------------ */

static void overlay_fail(const char *why)
{
  log_printf("song list off: %s", why);
  state = OV_FAILED;
}

static bool can_draw(const nvn_texture_info_t *info)
{
  return overlay_cpu_usable(info);
}

static bool record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info, nvn_rect_t area,
                   const overlay_panel_t *panel)
{
  return overlay_cpu_record(cmd, slot, texture, info, area, panel);
}

void overlay_before_present(nvn_queue_t *queue, nvn_window_t *window, nvn_texture_t *texture)
{
  const overlay_panel_t *panel = newest_panel();
  nvn_texture_info_t info;
  if (!panel->shown || state == OV_FAILED || !nvn_texture_info(texture, &info))
    return;
  if (state == OV_NONE) {
    if (!slots_init(COMMAND_BYTES)) {
      overlay_fail("no commands to draw with");
      return;
    }
    state = OV_READY;
  }
  if (!can_draw(&info))
    return;
  int slot = slots_acquire();
  if (slot < 0) { /* the GPU is behind: this frame goes without, rather than held up */
    if (slots_stuck())
      overlay_fail("the GPU didn't finish the previous drawing");
    return;
  }
  nvn_rect_t area = nvn_visible_area(window, &info);
  if (record(slots_begin(slot), slot, texture, &info, area, panel))
    slots_submit(queue, slot);
  else
    slots_discard();
}
