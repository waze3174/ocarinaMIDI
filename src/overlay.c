/* The song list's panel over the game's picture, drawn without shaders: the text is rasterised on the
 * CPU into a buffer in the swapchain's format and copied into the texture about to be presented
 * (nvnCommandBufferCopyBufferToTexture). Nothing is read back from the picture. Two slots (pixel
 * buffer, command memory, sync) alternate, and a slot is reused only once the GPU has finished with
 * it. Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3), cut down to one opaque panel. */
#include "overlay.h"

#include "font.h"
#include "nvn.h"
#include "sys.h"

void *aligned_alloc(size_t align, size_t size); /* from main */

enum {
  /* memory pool flags */
  POOL_CPU_UNCACHED = 0x02,
  POOL_GPU_UNCACHED = 0x10,
  POOL_GPU_CACHED = 0x20,
  SYNC_ALL_GPU_COMMANDS_COMPLETE = 0, /* nvnQueueFenceSync's condition */
  SYNC_TIMEOUT_EXPIRED = 2,           /* nvnSyncWait: lower results mean the GPU got there */
  /* the swapchain formats we can draw into */
  FMT_RGBA8 = 37,
  FMT_RGBA16F = 41,
  FMT_RGBX8_SRGB = 55,
  FMT_RGBA8_SRGB = 56,
  FMT_RGB10A2 = 61,
};

#define SYNC_TIMEOUT_NS     1000000000ull /* a second */
#define SLOTS               2
#define CMD_SIZE            0x10000 /* command memory per slot: far more than one copy needs */
#define CTRL_SIZE           0x4000  /* control memory per slot */
#define PAGE_SIZE           0x1000
#define MAX_BYTES_PER_PIXEL 8
/* screen pixels per font pixel: one more for each SCALE_STEP_LINES lines of picture (2 at 1080p) */
#define SCALE_STEP_LINES    480
#define MAX_SCALE           4
#define CELL_H              (FONT_H + 2) /* a text row and the gap under it */
#define BORDER_FONT_PX      4            /* the panel's edge around the text */
#define TOP_FONT_PX         8            /* from the top of the picture to the panel */
#define PANEL_FONT_W        (OVERLAY_COLS * FONT_W + 2 * BORDER_FONT_PX)
#define PANEL_FONT_H        (OVERLAY_ROWS * CELL_H - (CELL_H - FONT_H) + 2 * BORDER_FONT_PX)

/* The NVN functions we use, filled in by name from fn_names (in the same order). */
static struct {
  void (*pool_builder_defaults)(nvn_obj_t *);
  void (*pool_builder_device)(nvn_obj_t *, nvn_device_t *);
  void (*pool_builder_flags)(nvn_obj_t *, int);
  void (*pool_builder_storage)(nvn_obj_t *, void *, size_t);
  bool (*pool_init)(nvn_obj_t *, const nvn_obj_t *);
  nvn_addr_t (*pool_address)(const nvn_obj_t *);
  bool (*cmd_init)(nvn_obj_t *, nvn_device_t *);
  void (*cmd_add_command)(nvn_obj_t *, const nvn_obj_t *pool, ptrdiff_t offset, size_t size);
  void (*cmd_add_control)(nvn_obj_t *, void *, size_t);
  void (*cmd_begin)(nvn_obj_t *);
  nvn_handle_t (*cmd_end)(nvn_obj_t *);
  void (*cmd_copy_to_texture)(nvn_obj_t *, nvn_addr_t, const nvn_texture_t *, const void *view,
                              const nvn_region_t *, int flags);
  void (*queue_submit)(nvn_queue_t *, int, const nvn_handle_t *);
  void (*queue_fence)(nvn_queue_t *, nvn_obj_t *sync, int condition, int flags);
  bool (*sync_init)(nvn_obj_t *, nvn_device_t *);
  int (*sync_wait)(const nvn_obj_t *, uint64_t timeout_ns);
  int (*tex_width)(const nvn_texture_t *);
  int (*tex_height)(const nvn_texture_t *);
  int (*tex_format)(const nvn_texture_t *);
  void (*window_crop)(const nvn_window_t *, nvn_rect_t *);
} fn;

static const char *const fn_names[] = {
  "nvnMemoryPoolBuilderSetDefaults", "nvnMemoryPoolBuilderSetDevice", "nvnMemoryPoolBuilderSetFlags",
  "nvnMemoryPoolBuilderSetStorage", "nvnMemoryPoolInitialize", "nvnMemoryPoolGetBufferAddress",
  "nvnCommandBufferInitialize", "nvnCommandBufferAddCommandMemory", "nvnCommandBufferAddControlMemory",
  "nvnCommandBufferBeginRecording", "nvnCommandBufferEndRecording", "nvnCommandBufferCopyBufferToTexture",
  "nvnQueueSubmitCommands", "nvnQueueFenceSync", "nvnSyncInitialize", "nvnSyncWait", "nvnTextureGetWidth",
  "nvnTextureGetHeight", "nvnTextureGetFormat", "nvnWindowGetCrop",
};
#define FN_COUNT (sizeof(fn_names) / sizeof(*fn_names))
_Static_assert(FN_COUNT == sizeof(fn) / sizeof(void *), "fn table");

static const uint8_t style_rgb[OVERLAY_STYLES][3] = {
  [OVERLAY_TEXT] = { 0xFF, 0xFF, 0xFF },
  [OVERLAY_DIM] = { 0x90, 0x90, 0x90 },
  [OVERLAY_HEADING] = { 0xA0, 0xC8, 0xFF },
};
static const uint8_t background_rgb[3] = { 0x18, 0x18, 0x20 };

static enum { OV_NONE, OV_READY, OV_FAILED } state;
static nvn_obj_t cmd_buffer, pixel_pool, command_pool, slot_sync[SLOTS];
static uint8_t *pixel_mem, *command_mem, *control_mem;
static size_t slot_pixel_bytes;
static int swapchain_format, bytes_per_pixel, max_scale;
static unsigned frame_count;
static bool slot_used[SLOTS];
/* what each slot's pixel buffer holds, so it's only redrawn when that changes */
static overlay_panel_t slot_panel[SLOTS];
static int slot_scale[SLOTS];
static bool drawing_logged;

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

/* --- setting up ----------------------------------------------------------------------------------- */

static void overlay_fail(const char *why)
{
  log_printf("song list off: %s", why);
  state = OV_FAILED;
}

static size_t round_page(size_t n)
{
  return (n + PAGE_SIZE - 1) & ~(size_t)(PAGE_SIZE - 1);
}

static bool make_pool(nvn_obj_t *pool, void *mem, size_t size, int flags)
{
  nvn_obj_t builder;
  memset(&builder, 0, sizeof(builder));
  fn.pool_builder_defaults(&builder);
  fn.pool_builder_device(&builder, nvn_device());
  fn.pool_builder_flags(&builder, flags);
  fn.pool_builder_storage(&builder, mem, size);
  return fn.pool_init(pool, &builder);
}

/* bytes per pixel of a swapchain format we can draw into; 0 for any other */
static int format_bpp(int format)
{
  switch (format) {
    case FMT_RGBA8:
    case FMT_RGBA8_SRGB:
    case FMT_RGBX8_SRGB:
    case FMT_RGB10A2:
      return 4;
    case FMT_RGBA16F:
      return 8;
    default:
      return 0;
  }
}

static int scale_for(int height)
{
  int scale = height / SCALE_STEP_LINES;
  return scale < 1 ? 1 : scale > MAX_SCALE ? MAX_SCALE : scale;
}

static bool load_functions(void)
{
  void **slots = (void **)&fn;
  for (unsigned i = 0; i < FN_COUNT; i++) {
    slots[i] = nvn_proc(fn_names[i]);
    if (!slots[i]) {
      log_printf("NVN has no %s", fn_names[i]);
      return false;
    }
  }
  return true;
}

static bool allocate(void)
{
  slot_pixel_bytes =
    round_page((size_t)PANEL_FONT_W * PANEL_FONT_H * max_scale * max_scale * bytes_per_pixel);
  pixel_mem = aligned_alloc(PAGE_SIZE, slot_pixel_bytes * SLOTS);
  command_mem = aligned_alloc(PAGE_SIZE, CMD_SIZE * SLOTS);
  control_mem = aligned_alloc(PAGE_SIZE, CTRL_SIZE * SLOTS);
  return pixel_mem && command_mem && control_mem;
}

/* Once, at the first present with the panel shown. False until the game has a device. */
static bool overlay_init(const nvn_texture_t *texture)
{
  if (!nvn_device())
    return false;
  if (!load_functions()) {
    overlay_fail("an NVN function is missing");
    return false;
  }
  swapchain_format = fn.tex_format(texture);
  bytes_per_pixel = format_bpp(swapchain_format);
  int height = fn.tex_height(texture);
  log_printf("swapchain: %dx%d, format %d", fn.tex_width(texture), height, swapchain_format);
  if (!bytes_per_pixel) {
    overlay_fail("unsupported swapchain format (see the line above)");
    return false;
  }
  max_scale = scale_for(height); /* the buffers' size: a taller picture later keeps this scale */
  if (!allocate()) {
    overlay_fail("out of memory");
    return false;
  }
  if (!make_pool(&pixel_pool, pixel_mem, slot_pixel_bytes * SLOTS, POOL_CPU_UNCACHED | POOL_GPU_UNCACHED) ||
      !make_pool(&command_pool, command_mem, CMD_SIZE * SLOTS, POOL_CPU_UNCACHED | POOL_GPU_CACHED)) {
    overlay_fail("memory pool");
    return false;
  }
  if (!fn.cmd_init(&cmd_buffer, nvn_device())) {
    overlay_fail("command buffer");
    return false;
  }
  for (int s = 0; s < SLOTS; s++) {
    if (!fn.sync_init(&slot_sync[s], nvn_device())) {
      overlay_fail("sync");
      return false;
    }
  }
  log_printf("song list ready (scale up to %d, %u KiB of pixels)", max_scale,
             (unsigned)(slot_pixel_bytes * SLOTS / 1024));
  state = OV_READY;
  return true;
}

/* --- drawing ---------------------------------------------------------------------------------------- */

/* value / 255 as an IEEE half-precision float (0..1), from the single-precision bits */
static uint16_t to_half_float(uint8_t value)
{
  if (!value)
    return 0;
  float f = value / 255.0f;
  uint32_t bits;
  memcpy(&bits, &f, 4);
  int exponent = (int)((bits >> 23) & 0xFF) - 127 + 15; /* rebiased from float's to half's */
  return (uint16_t)(exponent << 10 | ((bits >> 13) & 0x3FF));
}

/* an opaque colour in the swapchain's format */
static uint64_t encode_pixel(const uint8_t rgb[3])
{
  switch (swapchain_format) {
    case FMT_RGB10A2:
      return (uint32_t)(rgb[0] * 1023 / 255) | (uint32_t)(rgb[1] * 1023 / 255) << 10 |
             (uint32_t)(rgb[2] * 1023 / 255) << 20 | 3u << 30;
    case FMT_RGBA16F: /* 0x3C00 is 1.0 */
      return to_half_float(rgb[0]) | (uint64_t)to_half_float(rgb[1]) << 16 | (uint64_t)to_half_float(rgb[2]) << 32 |
             (uint64_t)0x3C00 << 48;
    default:
      return rgb[0] | rgb[1] << 8 | rgb[2] << 16 | 0xFFu << 24;
  }
}

static bool font_pixel(char c, int x, int y)
{
  unsigned glyph = (unsigned char)c - FONT_FIRST;
  return glyph < FONT_COUNT && (font_8x8[glyph][y] >> (FONT_W - 1 - x) & 1);
}

/* Whether pixel (x, y) of the text, in font pixels, is ink. */
static bool text_pixel(const overlay_panel_t *panel, int x, int y)
{
  if (x < 0 || y < 0)
    return false;
  int row = y / CELL_H, col = x / FONT_W;
  if (row >= OVERLAY_ROWS || col >= OVERLAY_COLS || y % CELL_H >= FONT_H)
    return false;
  return font_pixel(panel->text[row][col], x % FONT_W, y % CELL_H);
}

/* The ink of the text row at font pixel y (any for a y between rows: no ink is drawn there). */
static uint64_t row_ink(const uint64_t ink[OVERLAY_STYLES], const overlay_panel_t *panel, int y)
{
  int row = y / CELL_H;
  if (y < 0 || row >= OVERLAY_ROWS || panel->style[row] >= OVERLAY_STYLES)
    return ink[OVERLAY_TEXT];
  return ink[panel->style[row]];
}

static void put_pixel(uint8_t *row, int x, uint64_t colour)
{
  if (bytes_per_pixel == 8) {
    memcpy(row + (size_t)x * 8, &colour, 8);
  } else {
    uint32_t colour32 = (uint32_t)colour;
    memcpy(row + (size_t)x * 4, &colour32, 4);
  }
}

/* The panel at `scale` screen pixels per font pixel into `dst`, a row at a time: the GPU reads it
 * uncached, so each row is built in a cached buffer first. */
static void rasterise(const overlay_panel_t *panel, uint8_t *dst, int scale)
{
  static _Alignas(16) uint8_t row_buffer[PANEL_FONT_W * MAX_SCALE * MAX_BYTES_PER_PIXEL];
  uint64_t background = encode_pixel(background_rgb);
  uint64_t ink[OVERLAY_STYLES];
  for (int i = 0; i < OVERLAY_STYLES; i++)
    ink[i] = encode_pixel(style_rgb[i]);
  int w = PANEL_FONT_W * scale, h = PANEL_FONT_H * scale;
  size_t row_bytes = (size_t)w * bytes_per_pixel;
  for (int y = 0; y < h; y++) {
    int text_y = y / scale - BORDER_FONT_PX;
    uint64_t colour = row_ink(ink, panel, text_y);
    for (int x = 0; x < w; x++)
      put_pixel(row_buffer, x, text_pixel(panel, x / scale - BORDER_FONT_PX, text_y) ? colour : background);
    memcpy(dst + (size_t)y * row_bytes, row_buffer, row_bytes);
  }
}

/* The part of the texture that's shown: the game can render into a larger texture than it displays. */
static nvn_rect_t visible_area(const nvn_window_t *window, int texture_width, int texture_height)
{
  nvn_rect_t crop = { 0, 0, 0, 0 };
  if (window)
    fn.window_crop(window, &crop);
  if (crop.w <= 0 || crop.h <= 0 || crop.x < 0 || crop.y < 0 || crop.x + crop.w > texture_width ||
      crop.y + crop.h > texture_height)
    crop = (nvn_rect_t){ 0, 0, texture_width, texture_height };
  return crop;
}

static void submit_copy(nvn_queue_t *queue, int slot, nvn_texture_t *texture, const nvn_region_t *region)
{
  __asm__ volatile("dsb sy" ::: "memory"); /* the pixels reach memory before the GPU copies them */
  fn.cmd_add_command(&cmd_buffer, &command_pool, (ptrdiff_t)slot * CMD_SIZE, CMD_SIZE);
  fn.cmd_add_control(&cmd_buffer, control_mem + (size_t)slot * CTRL_SIZE, CTRL_SIZE);
  fn.cmd_begin(&cmd_buffer);
  nvn_addr_t source = fn.pool_address(&pixel_pool) + (nvn_addr_t)slot * slot_pixel_bytes;
  fn.cmd_copy_to_texture(&cmd_buffer, source, texture, 0, region, 0);
  nvn_handle_t handle = fn.cmd_end(&cmd_buffer);
  fn.queue_submit(queue, 1, &handle);
  fn.queue_fence(queue, &slot_sync[slot], SYNC_ALL_GPU_COMMANDS_COMPLETE, 0);
  slot_used[slot] = true;
}

void overlay_before_present(nvn_queue_t *queue, nvn_window_t *window, nvn_texture_t *texture)
{
  const overlay_panel_t *panel = newest_panel();
  if (!panel->shown || state == OV_FAILED)
    return;
  if (state == OV_NONE && !overlay_init(texture))
    return;
  if (fn.tex_format(texture) != swapchain_format) {
    overlay_fail("the swapchain's format changed");
    return;
  }
  int texture_width = fn.tex_width(texture), texture_height = fn.tex_height(texture);
  nvn_rect_t area = visible_area(window, texture_width, texture_height);
  int scale = scale_for(area.h) < max_scale ? scale_for(area.h) : max_scale;
  int w = PANEL_FONT_W * scale, h = PANEL_FONT_H * scale, top = TOP_FONT_PX * scale;
  if (w > area.w || top + h > area.h)
    return;
  int slot = frame_count++ % SLOTS;
  if (slot_used[slot] && fn.sync_wait(&slot_sync[slot], SYNC_TIMEOUT_NS) >= SYNC_TIMEOUT_EXPIRED) {
    overlay_fail("the GPU didn't finish the previous copy");
    return;
  }
  if (slot_scale[slot] != scale || memcmp(&slot_panel[slot], panel, sizeof(*panel))) {
    rasterise(panel, pixel_mem + (size_t)slot * slot_pixel_bytes, scale);
    memcpy(&slot_panel[slot], panel, sizeof(*panel));
    slot_scale[slot] = scale;
  }
  nvn_region_t region = { area.x + (area.w - w) / 2, area.y + top, 0, w, h, 1 };
  submit_copy(queue, slot, texture, &region);
  if (!drawing_logged) {
    drawing_logged = true;
    log_printf("song list on screen: %dx%d at %d,%d of %dx%d", w, h, region.x, region.y, texture_width,
               texture_height);
  }
}
