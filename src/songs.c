#include "songs.h"

#include "sdfs.h"
#include "sys.h"

#define PLAYLIST_FILE  SONGS_DIR "/playlist.txt"
#define MAX_SONGS      64
#define MAX_NAME_LEN   64
#define PLAYLIST_BYTES (MAX_SONGS * (MAX_NAME_LEN + 2))
#define SONG_BYTES     (256 * 1024)
#define PATH_LEN       (sizeof(SONGS_DIR) + MAX_NAME_LEN + 1)

static bool sd_mounted;
static char song_names[MAX_SONGS][MAX_NAME_LEN];
static int song_count;
static char playlist_text[PLAYLIST_BYTES + 1];
static uint8_t song_bytes[SONG_BYTES] __attribute__((aligned(8)));
static song_t loaded_song;

static bool mount_sd(void)
{
  if (sd_mounted)
    return true;
  nn_result_t result = fs_mount_sd(SD_MOUNT);
  if (result != 0 && fs_mount_sd_debug(SD_MOUNT) != 0) {
    log_printf("can't mount the SD card (0x%x)", result);
    return false;
  }
  sd_mounted = true;
  return true;
}

/* The whole file in buf; its size, or -1 (logged). */
static int64_t read_file(const char *path, void *buf, size_t capacity)
{
  fs_file_t file;
  nn_result_t result = fs_open(&file, path, FS_READ);
  if (result != 0) {
    log_printf("can't open %s (0x%x)", path, result);
    return -1;
  }
  int64_t size = -1;
  size_t got = 0;
  result = fs_size(&size, file);
  if (result == 0 && size >= 0 && (uint64_t)size <= capacity)
    result = fs_read(&got, file, 0, buf, (size_t)size);
  fs_close(file);
  if (result != 0 || size < 0 || (uint64_t)size > capacity || got != (size_t)size) {
    log_printf("can't read %s (0x%x, %lld bytes, limit %u)", path, result, (long long)size, (unsigned)capacity);
    return -1;
  }
  return size;
}

static void song_path(char *path, size_t size, const char *name)
{
  snprintf(path, size, SONGS_DIR "/%s", name);
}

static bool song_file_exists(const char *name)
{
  char path[PATH_LEN];
  song_path(path, sizeof(path), name);
  fs_file_t file;
  if (fs_open(&file, path, FS_READ) != 0)
    return false;
  fs_close(file);
  return true;
}

static bool is_space(char c)
{
  return c == ' ' || c == '\t' || c == '\r';
}

/* One playlist line: blank lines, lines starting with '#' and missing files are skipped. */
static void add_song_name(const char *line, size_t len)
{
  while (len && is_space(*line)) {
    line++;
    len--;
  }
  while (len && is_space(line[len - 1]))
    len--;
  if (!len || line[0] == '#')
    return;
  if (len >= MAX_NAME_LEN || song_count >= MAX_SONGS) {
    log_printf("playlist: skipped a line (names up to %d characters, up to %d songs)", MAX_NAME_LEN - 1, MAX_SONGS);
    return;
  }
  char *name = song_names[song_count];
  memcpy(name, line, len);
  name[len] = 0;
  if (!song_file_exists(name)) {
    log_printf("playlist: %s is missing, skipped", name);
    return;
  }
  song_count++;
}

bool songs_reload(void)
{
  song_count = 0;
  if (!mount_sd())
    return false;
  int64_t size = read_file(PLAYLIST_FILE, playlist_text, PLAYLIST_BYTES);
  if (size < 0)
    return false;
  playlist_text[size] = 0;
  const char *line = playlist_text;
  for (const char *p = playlist_text;; p++) {
    if (*p == '\n' || !*p) {
      add_song_name(line, (size_t)(p - line));
      line = p + 1;
    }
    if (!*p)
      break;
  }
  if (!song_count)
    log_printf("%s lists no song that is on the SD card", PLAYLIST_FILE);
  return song_count > 0;
}

int songs_count(void)
{
  return song_count;
}

int songs_step(int index, int step)
{
  return song_count ? ((index + step) % song_count + song_count) % song_count : 0;
}

const char *songs_name(int index)
{
  return index >= 0 && index < song_count ? song_names[index] : "";
}

static const char *song_problem(const song_header_t *header, int64_t size)
{
  if ((uint64_t)size < sizeof(song_header_t) || header->magic != SONG_MAGIC)
    return "not a song file";
  if (header->version != SONG_VERSION)
    return "made by a different converter version";
  if (!header->ticks_per_second)
    return "no tick rate";
  if (header->event_count > (uint64_t)(size - (int64_t)sizeof(song_header_t)) / sizeof(song_event_t))
    return "cut short";
  const song_event_t *events = (const song_event_t *)(header + 1);
  for (uint32_t i = 1; i < header->event_count; i++)
    if (events[i].tick < events[i - 1].tick)
      return "events out of order";
  return 0;
}

const song_t *songs_load(int index)
{
  if (index < 0 || index >= song_count)
    return 0;
  char path[PATH_LEN];
  song_path(path, sizeof(path), song_names[index]);
  int64_t size = read_file(path, song_bytes, SONG_BYTES);
  if (size < 0)
    return 0;
  song_header_t *header = (song_header_t *)song_bytes;
  const char *problem = song_problem(header, size);
  if (problem) {
    log_printf("%s: %s", path, problem);
    return 0;
  }
  header->title[SONG_TITLE_LEN - 1] = 0;
  loaded_song.header = header;
  loaded_song.events = (const song_event_t *)(header + 1);
  return &loaded_song;
}
