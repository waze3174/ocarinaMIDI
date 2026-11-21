/* Before each of the game's presents (nvn.c): draws the song list, if it's shown, in the game's own style
 * (gameui.c) or, when that can't be, in the plain panel (overlay_cpu.c), and either way as one
 * command buffer on a slot (slots.c). The panel itself comes from the game's controller thread
 * (songlist.c). Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3). */
#include "overlay.h"

#include "gameui.h"
#include "nvn.h"
#include "overlay_cpu.h"
#include "slots.h"
#include "sys.h"

#define COMMAND_BYTES 0x20000 /* command memory per slot: far more than a panel's 150 quads need */
#define RETRY_MS      5000    /* between tries when the game's heap has no room yet */

/* what is set up next, in order; the plain panel only if the game's style can't be used */
static enum { OV_SLOTS, OV_GAMEUI, OV_PLAIN, OV_READY, OV_FAILED } state;
static uint64_t retry_at_ms;

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

/* Whether either panel can draw on this picture: the game's style, else the plain one. */
static bool can_draw(const nvn_texture_info_t *info)
{
  return gameui_usable() || overlay_cpu_usable(info);
}

/* Records the panel into the slot's commands, in the game's style if it can be. */
static bool record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info, nvn_rect_t area,
                   const overlay_panel_t *panel)
{
  if (gameui_usable())
    return gameui_record(cmd, slot, texture, info, area, panel);
  return overlay_cpu_record(cmd, slot, texture, info, area, panel);
}

static init_result_t prepare_step(const nvn_texture_info_t *info)
{
  switch (state) {
    case OV_SLOTS: return slots_init(COMMAND_BYTES);
    case OV_GAMEUI: return gameui_init();
    default: return overlay_cpu_init(info);
  }
}

static void prepare_done(init_result_t result)
{
  bool ok = result == INIT_OK;
  switch (state) {
    case OV_SLOTS:
      if (ok)
        state = OV_GAMEUI;
      else
        overlay_fail("no commands to draw with");
      break;
    case OV_GAMEUI: state = ok ? OV_READY : OV_PLAIN; break;
    default: state = ok ? OV_READY : OV_FAILED; break; /* overlay_cpu.c said why */
  }
}

/* Takes the memory the list needs, one step a present, as soon as the game's files are read (gameui.h)
 * rather than when the list is first shown: the game's heap fills up as it plays. A step that finds no
 * room is tried again after RETRY_MS; any other failure is for good. */
static void prepare(const nvn_texture_info_t *info)
{
  if (!gameui_settled() || sys_ms() < retry_at_ms)
    return;
  init_result_t result = prepare_step(info);
  if (result == INIT_NO_MEMORY) {
    log_printf("song list: no memory yet, trying again in %d s", RETRY_MS / 1000);
    retry_at_ms = sys_ms() + RETRY_MS;
    return;
  }
  prepare_done(result);
}

void overlay_before_present(nvn_queue_t *queue, nvn_window_t *window, nvn_texture_t *texture)
{
  const overlay_panel_t *panel = newest_panel();
  nvn_texture_info_t info;
  if (state == OV_FAILED || (state == OV_READY && !panel->shown) || !nvn_texture_info(texture, &info))
    return;
  if (state != OV_READY) {
    prepare(&info);
    return;
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
