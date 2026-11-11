/* ocarinaMIDI: plays songs converted from MIDI files on Ocarina of Time's (Switch 2) ocarina, by
 * pressing the ocarina's buttons for the player. Loaded by the game as subsdk8; see docs/DESIGN.md. */
#include "hooks.h"
#include "sys.h"

/* exported by main */
extern void nnMain(void);

__attribute__((used)) void ocarina_midi_module_init(void)
{
  uintptr_t main_base = sys_region_start((uintptr_t)&nnMain);
  const char *error = main_base ? hooks_init(main_base) : "the game's main module wasn't found";
  if (error) {
    log_raw("not started:");
    log_raw(error);
    return;
  }
  log_raw("loaded " PACKAGE_VERSION "; controller hooks go in at the game's first controller setup");
}
