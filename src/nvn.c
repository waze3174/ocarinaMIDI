/* Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3). */
#include "nvn.h"

#include "got.h"
#include "sys.h"

#define MAX_SWAPCHAIN_TEXTURES 8

typedef void *(*bootstrap_loader_t)(const char *name);
typedef void *(*getproc_t)(nvn_device_t *device, const char *name);
typedef void (*present_t)(nvn_queue_t *queue, nvn_window_t *window, int texture_index);
typedef void (*set_textures_t)(void *builder, int count, nvn_texture_t *const *textures);
typedef bool (*device_init_t)(nvn_device_t *device, const void *builder);

extern void *nvnBootstrapLoader(const char *name); /* from sdk */

/* What our wrappers call: another add-on's wrapper (sloperinaGZ's), or NVN's own function. */
static void *next_bootstrap_loader, *next_getproc, *next_present, *next_set_textures, *next_device_init;
static nvn_device_t *device;
static nvn_texture_t *swapchain_textures[MAX_SWAPCHAIN_TEXTURES];
static int swapchain_texture_count;

static void hook_present(nvn_queue_t *queue, nvn_window_t *window, int index)
{
  static bool warned;
  int count = __atomic_load_n(&swapchain_texture_count, __ATOMIC_ACQUIRE);
  if (index >= 0 && index < count) {
    overlay_before_present(queue, window, swapchain_textures[index]);
  } else if (!warned) {
    warned = true;
    log_printf("present of swapchain texture %d, but %d seen: no song list", index, count);
  }
  ((present_t)next_present)(queue, window, index);
}

static void hook_set_textures(void *builder, int count, nvn_texture_t *const *textures)
{
  int kept = count < MAX_SWAPCHAIN_TEXTURES ? count : MAX_SWAPCHAIN_TEXTURES;
  __atomic_store_n(&swapchain_texture_count, 0, __ATOMIC_RELEASE); /* none usable while it's rewritten */
  for (int i = 0; i < kept; i++)
    swapchain_textures[i] = textures[i];
  __atomic_store_n(&swapchain_texture_count, kept, __ATOMIC_RELEASE);
  ((set_textures_t)next_set_textures)(builder, count, textures);
}

static bool hook_device_init(nvn_device_t *dev, const void *builder)
{
  bool ok = ((device_init_t)next_device_init)(dev, builder);
  if (ok)
    device = dev;
  return ok;
}

static void *hook_getproc(nvn_device_t *dev, const char *name);

static const struct {
  const char *name;
  void *hook;
  void **next;
} wrapped[] = {
  { "nvnDeviceGetProcAddress", (void *)hook_getproc, &next_getproc },
  { "nvnQueuePresentTexture", (void *)hook_present, &next_present },
  { "nvnWindowBuilderSetTextures", (void *)hook_set_textures, &next_set_textures },
  { "nvnDeviceInitialize", (void *)hook_device_init, &next_device_init },
};
#define WRAPPED_COUNT (sizeof(wrapped) / sizeof(*wrapped))

static bool names_equal(const char *a, const char *b)
{
  while (*a && *a == *b) {
    a++;
    b++;
  }
  return *a == *b;
}

/* What the game gets for a function it looks up: our wrapper, if it's one we wrap. */
static void *wrap(const char *name, void *proc)
{
  if (!proc)
    return proc;
  for (size_t i = 0; i < WRAPPED_COUNT; i++) {
    if (!names_equal(name, wrapped[i].name))
      continue;
    if (proc != wrapped[i].hook) /* never our own wrapper: it would call itself */
      *wrapped[i].next = proc;
    return wrapped[i].hook;
  }
  return proc;
}

static void *hook_getproc(nvn_device_t *dev, const char *name)
{
  if (dev && !device)
    device = dev;
  return wrap(name, ((getproc_t)next_getproc)(dev, name));
}

static void *hook_bootstrap_loader(const char *name)
{
  return wrap(name, ((bootstrap_loader_t)next_bootstrap_loader)(name));
}

const char *nvn_hook_game(uintptr_t main_base)
{
  return got_hook(main_base, "nvnBootstrapLoader", (void *)hook_bootstrap_loader, (void *)nvnBootstrapLoader,
                  &next_bootstrap_loader);
}

nvn_device_t *nvn_device(void)
{
  return device;
}

void *nvn_proc(const char *name)
{
  return device && next_getproc ? ((getproc_t)next_getproc)(device, name) : 0;
}
