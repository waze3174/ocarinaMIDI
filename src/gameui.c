/* The song list in the game's own style (see gameui.h). The look is sloperinaGZ's menu in its game style
 * (src/ootgz/nativeui.c, GPL-3; master 8c3a940636), at its sizes: a box near black and solid with hard
 * edges, the title in the game's gold (DemiBold) over a hairline, the songs in Clarimo UD PE, and the
 * selected one in DemiBold white on a light band that fades out at both ends. What sloperinaGZ also draws
 * with the game's pictures (the options cursor round the selection, the ornament line) comes from files
 * this module doesn't read, so the band and a plain hairline stand in, as they do in sloperinaGZ until its
 * pictures are loaded. */
#include "gameui.h"

#include "gamefont.h"
#include "gpuui.h"
#include "slots.h"
#include "sys.h"
#include "uishader.h"

/* Sizes are in font pixels (fp), sloperinaGZ's unit: a 360th of the picture's height (3 pixels at 1080p). */
#define PICTURE_LINES_PER_FP 360.0f
#define MARGIN_TOP_FP        8
#define BOX_PAD_X_FP         14
#define BOX_PAD_Y_FP         12
#define TITLE_ROW_FP         15
#define TITLE_TEXT_FP        11
#define TITLE_GAP_FP         11    /* under the title row: its hairline is a bit above the middle */
#define TITLE_RULE_AT        0.42f /* of that gap */
#define TITLE_RULE_OVER_FP   6     /* the hairline reaches this far past the text on each side */
#define SONG_ROW_FP          13
#define SONG_TEXT_FP         9
#define BAND_OVER_FP         8     /* the selection band reaches this far past the text on each side */
#define MIN_CONTENT_FP       120
#define STATE_GAP_EM         1.5f  /* between the place in the list and the state, in the title's em */
#define CAP_HEIGHT_EM        0.66f /* the capitals' height when the font has no 'H' */
#define MIN_LINE_PX          1.0f
#define LINE_FP              0.5f  /* a hairline's thickness */

/* opacities: the box is the game's info box (sloperinaGZ's menu at its default backdrop, 60%, on its curve) */
#define BOX_OPACITY       0.84f
#define RULE_OPACITY      0.6f
#define BAND_OPACITY      0.16f
#define BAND_LINE_OPACITY 0.45f
#define BAND_FADE_IN      0.08f /* of the band's width */
#define BAND_FADE_OUT     0.4f

typedef struct { uint8_t r, g, b; } rgb_t;

static const rgb_t box_colour = { 0x0A, 0x09, 0x08 };
static const rgb_t band_colour = { 0xFF, 0xF4, 0xDC };
static const rgb_t title_colour = { 0xF5, 0xD6, 0x85 };
static const rgb_t song_colour = { 0xEC, 0xE8, 0xDE };
static const rgb_t selected_colour = { 0xFF, 0xFF, 0xFF };
static const rgb_t dim_colour = { 0x96, 0x91, 0x87 };

/* what loading the game's files came to: set on the game thread, read on the render thread */
static enum { LOAD_NONE, LOAD_OK, LOAD_FAILED } load_state;
static enum { GPU_NONE, GPU_READY, GPU_FAILED } gpu_state;

void gameui_load(void)
{
  if (__atomic_load_n(&load_state, __ATOMIC_ACQUIRE) != LOAD_NONE)
    return;
  /* the shader first: both read the same zstd dictionary, which the font loader lets go of */
  bool ok = uishader_load() && gamefont_load();
  if (!ok)
    log_printf("the game's font or UI shader can't be read: the song list uses its plain panel");
  __atomic_store_n(&load_state, ok ? LOAD_OK : LOAD_FAILED, __ATOMIC_RELEASE);
}

bool gameui_usable(void)
{
  if (gpu_state == GPU_READY)
    return true;
  if (gpu_state == GPU_FAILED || __atomic_load_n(&load_state, __ATOMIC_ACQUIRE) != LOAD_OK)
    return false;
  gpu_state = gpuui_init() ? GPU_READY : GPU_FAILED;
  if (gpu_state == GPU_FAILED)
    log_printf("game-style drawing can't start: the song list uses its plain panel");
  return gpu_state == GPU_READY;
}

/* --- type ------------------------------------------------------------------------------------------- */

typedef struct {
  gf_face_t face;
  int em;
  float cap; /* the capitals' height in pixels */
} type_t;

static type_t type_for(gf_face_t face, int text_fp, float fp)
{
  type_t t = { face, gamefont_em_for_height(face, (int)(text_fp * fp + 0.5f)), 0 };
  const gf_glyph_t *h = gamefont_glyph(face, t.em, 'H');
  t.cap = h && h->h > 0 ? (float)-h->y0 : t.em * CAP_HEIGHT_EM;
  return t;
}

static float text_width(const type_t *t, const char *s)
{
  return gamefont_measure(t->face, t->em, s, (int)strlen(s)) / 64.0f;
}

/* The baseline that centres the capitals in a row. */
static float baseline_in(const type_t *t, float row_top, float row_height)
{
  return (float)(int)(row_top + (row_height + t->cap) / 2 + 0.5f);
}

static gpu_colour_t to_gpu(rgb_t c, float alpha)
{
  return (gpu_colour_t){ c.r / 255.0f, c.g / 255.0f, c.b / 255.0f, alpha };
}

/* The text with its pen at x on the baseline, kerned; returns its width. */
static float draw_text(const type_t *t, const char *s, float x, float baseline, rgb_t colour)
{
  float pen = x;
  for (; *s; s++) {
    unsigned char c = (unsigned char)*s;
    float advance = gpuui_glyph_shadowed(t->face, t->em, c, pen, baseline, to_gpu(colour, 1));
    if (!advance && c != '?')
      advance = gpuui_glyph_shadowed(GF_REGULAR, t->em, '?', pen, baseline, to_gpu(colour, 1));
    pen += advance;
    if (s[1])
      pen += gamefont_kern(t->face, t->em, c, (unsigned char)s[1]) / 64.0f;
  }
  return pen - x;
}

/* --- shapes ----------------------------------------------------------------------------------------- */

/* A band from x0 to x1 that fades in over the first `in` of it and out over the last `out`. */
static void faded_strip(float x0, float x1, float y, float h, float in, float out, rgb_t colour, float alpha)
{
  float w = x1 - x0;
  if (w <= 0 || h <= 0)
    return;
  float stops[4] = { 0, in, 1 - out, 1 };
  for (int k = 0; k < 3; k++) {
    float a0 = k == 0 ? 0 : alpha, a1 = k == 2 ? 0 : alpha;
    float xa = x0 + stops[k] * w, xb = x0 + stops[k + 1] * w;
    gpu_colour_t corners[4] = { to_gpu(colour, a0), to_gpu(colour, a1), to_gpu(colour, a0), to_gpu(colour, a1) };
    gpuui_rect(xa, y, xb - xa, h, corners);
  }
}

/* The light band behind the selected song, with a hairline along its top and bottom. */
static void draw_selection(float x0, float x1, float y, float h, float line)
{
  faded_strip(x0, x1, y, h, BAND_FADE_IN, BAND_FADE_OUT, band_colour, BAND_OPACITY);
  faded_strip(x0, x1, y, line, BAND_FADE_IN, BAND_FADE_OUT, band_colour, BAND_LINE_OPACITY);
  faded_strip(x0, x1, y + h - line, line, BAND_FADE_IN, BAND_FADE_OUT, band_colour, BAND_LINE_OPACITY);
}

/* --- the panel -------------------------------------------------------------------------------------- */

typedef struct {
  float fp; /* screen pixels per font pixel */
  type_t title, state, song, selected;
  float content_w; /* the text's width: the widest of the title and the songs */
  int lines;       /* songs to draw */
  float box_x, box_y, box_w, box_h;
} layout_t;

static float title_width(const layout_t *l, const overlay_panel_t *panel)
{
  float w = text_width(&l->title, panel->where);
  return panel->state[0] ? w + l->title.em * STATE_GAP_EM + text_width(&l->state, panel->state) : w;
}

static const type_t *line_type(const layout_t *l, const overlay_panel_t *panel, int line)
{
  return line == panel->selected ? &l->selected : &l->song;
}

static void measure(layout_t *l, const overlay_panel_t *panel, nvn_rect_t area)
{
  l->fp = area.h / PICTURE_LINES_PER_FP;
  l->title = type_for(GF_BOLD, TITLE_TEXT_FP, l->fp);
  l->state = type_for(GF_REGULAR, TITLE_TEXT_FP, l->fp);
  l->song = type_for(GF_REGULAR, SONG_TEXT_FP, l->fp);
  l->selected = type_for(GF_BOLD, SONG_TEXT_FP, l->fp);
  float title_w = title_width(l, panel), min_w = MIN_CONTENT_FP * l->fp;
  l->content_w = title_w > min_w ? title_w : min_w;
  l->lines = 0;
  for (int i = 0; i < OVERLAY_LINES; i++) {
    if (!panel->line[i][0])
      continue;
    float w = text_width(line_type(l, panel, i), panel->line[i]);
    l->content_w = w > l->content_w ? w : l->content_w;
    l->lines++;
  }
  l->box_w = l->content_w + 2 * BOX_PAD_X_FP * l->fp;
  l->box_h = (2 * BOX_PAD_Y_FP + TITLE_ROW_FP + TITLE_GAP_FP + l->lines * SONG_ROW_FP) * l->fp;
  l->box_x = (float)(int)((area.w - l->box_w) / 2);
  l->box_y = (float)(int)(MARGIN_TOP_FP * l->fp);
}

static void draw_title(const layout_t *l, const overlay_panel_t *panel, float x, float y, float line)
{
  float row_h = TITLE_ROW_FP * l->fp;
  draw_text(&l->title, panel->where, x, baseline_in(&l->title, y, row_h), title_colour);
  if (panel->state[0]) {
    float state_x = x + l->content_w - text_width(&l->state, panel->state);
    draw_text(&l->state, panel->state, state_x, baseline_in(&l->state, y, row_h), dim_colour);
  }
  float over = TITLE_RULE_OVER_FP * l->fp;
  float rule_y = y + row_h + TITLE_GAP_FP * l->fp * TITLE_RULE_AT - line / 2;
  gpuui_fill(x - over, rule_y, l->content_w + 2 * over, line, to_gpu(dim_colour, RULE_OPACITY));
}

static void draw_songs(const layout_t *l, const overlay_panel_t *panel, float x, float y, float line)
{
  float row_h = SONG_ROW_FP * l->fp, over = BAND_OVER_FP * l->fp;
  for (int i = 0; i < OVERLAY_LINES; i++) {
    if (!panel->line[i][0])
      continue;
    bool selected = i == panel->selected;
    const type_t *t = line_type(l, panel, i);
    if (selected)
      draw_selection(x - over, x + l->content_w + over, y, row_h, line);
    draw_text(t, panel->line[i], x, baseline_in(t, y, row_h), selected ? selected_colour : song_colour);
    y += row_h;
  }
}

static void draw_panel(const overlay_panel_t *panel, nvn_rect_t area)
{
  layout_t l;
  measure(&l, panel, area);
  float line = l.fp * LINE_FP < MIN_LINE_PX ? MIN_LINE_PX : (float)(int)(l.fp * LINE_FP + 0.5f);
  gpuui_fill(l.box_x, l.box_y, l.box_w, l.box_h, to_gpu(box_colour, BOX_OPACITY));
  float x = l.box_x + BOX_PAD_X_FP * l.fp, y = l.box_y + BOX_PAD_Y_FP * l.fp;
  draw_title(&l, panel, x, y, line);
  draw_songs(&l, panel, x, y + (TITLE_ROW_FP + TITLE_GAP_FP) * l.fp, line);
}

bool gameui_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info, nvn_rect_t area,
                   const overlay_panel_t *panel)
{
  if (area.h <= 0)
    return false;
  if (gpuui_atlas_resetting() && !slots_wait_idle())
    return false;
  gpuui_begin(texture, area, info->height, nvn_origin_lower_left(), slot);
  draw_panel(panel, area);
  return gpuui_end(cmd, nvn_game_texture_pool(), nvn_game_sampler_pool());
}
