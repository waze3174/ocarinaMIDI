/* Redirect a module's imports by rewriting its GOT entries (after rtld has linked it).
 * Adapted from sloperinaGZ's src/ootgz/got.h (GPL-3). */
#ifndef GOT_H
#define GOT_H

#include <stdint.h>

/* Address of `module`'s GOT slot for imported symbol `name` (via its MOD0 and dynamic
 * section), or 0. */
uintptr_t *got_slot(uintptr_t module, const char *name);

/* Points the slot at `replacement`. *previous gets the slot's old value first, so a wrapper can
 * call it as soon as the slot points at it. Returns 0 on success, or a message. */
const char *got_hook(uintptr_t module, const char *name, void *replacement, void **previous);

#endif
