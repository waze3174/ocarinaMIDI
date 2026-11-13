/* The song list's plain panel over the game's picture, drawn without shaders: the text is rasterised on
 * the CPU into a buffer in the swapchain's format and copied into the texture about to be presented
 * (nvnCommandBufferCopyBufferToTexture). Nothing is read back from the picture. Each recording slot
 * (slots.c) has its own pixel buffer. Used when the game's own style (gameui.c) can't be. Adapted from
 * sloperinaGZ's src/ootgz/nvn.c (GPL-3), cut down to one opaque panel. */
#include "overlay_cpu.h"

#include "font.h"
#include "slots.h"
#include "sys.h"

void *aligned_alloc(size_t align, size_t size); /* from main */

enum {
  /* the swapchain formats we can draw into */
  FMT_RGBA8 = 37,
  FMT_RGBA16F = 41,
  FMT_RGBX8_SRGB = 55,
  FMT_RGBA8_SRGB = 56,
  FMT_RGB10A2 = 61,
};

#define PAGE_SIZE           0x1000
#define MAX_BYTES_PER_PIXEL 8
#define HALF_ONE            0x3C00 /* 1.0 as an IEEE half-precision float */
/* screen pixels per font pixel: one more for each SCALE_STEP_LINES lines of picture (2 at 1080p) */
#define SCALE_STEP_LINES    480
#define MAX_SCALE           4
#define CELL_H              (FONT_H + 2) /* a text row and the gap under it */
#define BORDER_FONT_PX      4            /* the panel's edge around the text */
#define TOP_FONT_PX         8            /* from the top of the picture to the panel */
#define ROWS                (1 + OVERLAY_LINES) /* the heading, then the songs */
#define PANEL_FONT_W        (OVERLAY_COLS * FONT_W + 2 * BORDER_FONT_PX)
#define PANEL_FONT_H        (ROWS * CELL_H - (CELL_H - FONT_H) + 2 * BORDER_FONT_PX)
#define SELECTED_MARKER     "> "
#define OTHER_MARKER        "  "
_Static_assert(sizeof(SELECTED_MARKER) - 1 == OVERLAY_MARKER_COLS, "marker width");
_Static_assert(sizeof(OTHER_MARKER) - 1 == OVERLAY_MARKER_COLS, "marker width");

/* The NVN functions we use, filled in by name from fn_names (in the same order). */
static struct {
  nvn_addr_t (*pool_address)(const nvn_obj_t *);
  void (*cmd_copy_to_texture)(nvn_obj_t *, nvn_addr_t, const nvn_texture_t *, const void *view,
                              const nvn_region_t *, int flags);
} fn;

static const char *const fn_names[] = { "nvnMemoryPoolGetBufferAddress", "nvnCommandBufferCopyBufferToTexture" };
#define FN_COUNT (sizeof(fn_names) / sizeof(*fn_names))
_Static_assert(FN_COUNT == sizeof(fn) / sizeof(void *), "fn table");

typedef enum { ROW_TEXT, ROW_DIM, ROW_HEADING, ROW_STYLES } row_style_t;

/* the panel as the text rows the font draws */
typedef struct {
  uint8_t style[ROWS]; /* row_style_t */
  char text[ROWS][OVERLAY_COLS + 1]; /* ASCII, NUL padded */
} rows_t;

static const uint8_t style_rgb[ROW_STYLES][3] = {
  [ROW_TEXT] = { 0xFF, 0xFF, 0xFF },
  [ROW_DIM] = { 0x90, 0x90, 0x90 },
  [ROW_HEADING] = { 0xA0, 0xC8, 0xFF },
};
static const uint8_t background_rgb[3] = { 0x18, 0x18, 0x20 };

static enum { CPU_NONE, CPU_READY, CPU_FAILED } state;
static nvn_obj_t pixel_pool;
static uint8_t *pixel_mem;
static size_t slot_pixel_bytes;
static int swapchain_format, bytes_per_pixel, max_scale;
/* what each slot's pixel buffer holds, so it's only redrawn when that changes */
static rows_t slot_rows[SLOT_COUNT];
static int slot_scale[SLOT_COUNT];
static bool drawing_logged;

/* --- the panel as text rows ----------------------------------------------------------------------- */

/* the state on the right of the heading's row, the place on the left; the place is cut if the two don't fit */
static void heading_row(char *row, const overlay_panel_t *panel)
{
  int state_len = (int)strlen(panel->state), where_len = (int)strlen(panel->where);
  int state_at = OVERLAY_COLS - state_len;
  if (where_len > state_at)
    where_len = state_at;
  memset(row, ' ', OVERLAY_COLS);
  memcpy(row, panel->where, (size_t)where_len);
  memcpy(row + state_at, panel->state, (size_t)state_len);
  row[OVERLAY_COLS] = 0;
}

static void song_row(rows_t *rows, int row, const overlay_panel_t *panel, int line)
{
  bool selected = line == panel->selected;
  bool plain = panel->selected < 0;
  rows->style[row] = selected || plain ? ROW_TEXT : ROW_DIM;
  snprintf(rows->text[row], OVERLAY_COLS + 1, "%s%s", selected ? SELECTED_MARKER : OTHER_MARKER, panel->line[line]);
}

static void make_rows(rows_t *rows, const overlay_panel_t *panel)
{
  memset(rows, 0, sizeof(*rows));
  rows->style[0] = ROW_HEADING;
  heading_row(rows->text[0], panel);
  for (int line = 0; line < OVERLAY_LINES; line++)
    if (panel->line[line][0])
      song_row(rows, 1 + line, panel, line);
}

/* --- setting up ----------------------------------------------------------------------------------- */

static void cpu_fail(const char *why)
{
  log_printf("song list off: %s", why);
  state = CPU_FAILED;
}

static size_t round_page(size_t n)
{
  return (n + PAGE_SIZE - 1) & ~(size_t)(PAGE_SIZE - 1);
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

/* Once, at the first present with the panel shown. */
static void cpu_init(const nvn_texture_info_t *info)
{
  if (!load_functions()) {
    cpu_fail("an NVN function is missing");
    return;
  }
  swapchain_format = info->format;
  bytes_per_pixel = format_bpp(swapchain_format);
  log_printf("swapchain: %dx%d, format %d", info->width, info->height, swapchain_format);
  if (!bytes_per_pixel) {
    cpu_fail("unsupported swapchain format (see the line above)");
    return;
  }
  max_scale = scale_for(info->height); /* the buffers' size: a taller picture later keeps this scale */
  slot_pixel_bytes = round_page((size_t)PANEL_FONT_W * PANEL_FONT_H * max_scale * max_scale * bytes_per_pixel);
  pixel_mem = aligned_alloc(PAGE_SIZE, slot_pixel_bytes * SLOT_COUNT);
  if (!pixel_mem) {
    cpu_fail("out of memory");
    return;
  }
  if (!nvn_make_pool(&pixel_pool, pixel_mem, slot_pixel_bytes * SLOT_COUNT,
                     NVN_POOL_CPU_UNCACHED | NVN_POOL_GPU_UNCACHED)) {
    cpu_fail("memory pool");
    return;
  }
  log_printf("song list ready (scale up to %d, %u KiB of pixels)", max_scale,
             (unsigned)(slot_pixel_bytes * SLOT_COUNT / 1024));
  state = CPU_READY;
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
    case FMT_RGBA16F:
      return to_half_float(rgb[0]) | (uint64_t)to_half_float(rgb[1]) << 16 | (uint64_t)to_half_float(rgb[2]) << 32 |
             (uint64_t)HALF_ONE << 48;
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
static bool text_pixel(const rows_t *rows, int x, int y)
{
  if (x < 0 || y < 0)
    return false;
  int row = y / CELL_H, col = x / FONT_W;
  if (row >= ROWS || col >= OVERLAY_COLS || y % CELL_H >= FONT_H)
    return false;
  return font_pixel(rows->text[row][col], x % FONT_W, y % CELL_H);
}

/* The ink of the text row at font pixel y (any for a y between rows: no ink is drawn there). */
static uint64_t row_ink(const uint64_t ink[ROW_STYLES], const rows_t *rows, int y)
{
  int row = y / CELL_H;
  if (y < 0 || row >= ROWS || rows->style[row] >= ROW_STYLES)
    return ink[ROW_TEXT];
  return ink[rows->style[row]];
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
static void rasterise(const rows_t *rows, uint8_t *dst, int scale)
{
  static _Alignas(16) uint8_t row_buffer[PANEL_FONT_W * MAX_SCALE * MAX_BYTES_PER_PIXEL];
  uint64_t background = encode_pixel(background_rgb);
  uint64_t ink[ROW_STYLES];
  for (int i = 0; i < ROW_STYLES; i++)
    ink[i] = encode_pixel(style_rgb[i]);
  int w = PANEL_FONT_W * scale, h = PANEL_FONT_H * scale;
  size_t row_bytes = (size_t)w * bytes_per_pixel;
  for (int y = 0; y < h; y++) {
    int text_y = y / scale - BORDER_FONT_PX;
    uint64_t colour = row_ink(ink, rows, text_y);
    for (int x = 0; x < w; x++)
      put_pixel(row_buffer, x, text_pixel(rows, x / scale - BORDER_FONT_PX, text_y) ? colour : background);
    memcpy(dst + (size_t)y * row_bytes, row_buffer, row_bytes);
  }
}

bool overlay_cpu_usable(const nvn_texture_info_t *info)
{
  if (state == CPU_NONE)
    cpu_init(info);
  if (state == CPU_READY && info->format != swapchain_format) {
    cpu_fail("the swapchain's format changed");
  }
  return state == CPU_READY;
}

bool overlay_cpu_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                        nvn_rect_t area, const overlay_panel_t *panel)
{
  int scale = scale_for(area.h) < max_scale ? scale_for(area.h) : max_scale;
  int w = PANEL_FONT_W * scale, h = PANEL_FONT_H * scale, top = TOP_FONT_PX * scale;
  if (w > area.w || top + h > area.h)
    return false;
  rows_t rows;
  make_rows(&rows, panel);
  if (slot_scale[slot] != scale || memcmp(&slot_rows[slot], &rows, sizeof(rows))) {
    rasterise(&rows, pixel_mem + (size_t)slot * slot_pixel_bytes, scale);
    memcpy(&slot_rows[slot], &rows, sizeof(rows));
    slot_scale[slot] = scale;
  }
  nvn_region_t region = { area.x + (area.w - w) / 2, area.y + top, 0, w, h, 1 };
  nvn_addr_t source = fn.pool_address(&pixel_pool) + (nvn_addr_t)slot * slot_pixel_bytes;
  fn.cmd_copy_to_texture(cmd, source, texture, 0, &region, 0);
  if (!drawing_logged) {
    drawing_logged = true;
    log_printf("song list on screen (plain): %dx%d at %d,%d of %dx%d", w, h, region.x, region.y, info->width,
               info->height);
  }
  return true;
}
