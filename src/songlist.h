/* The song list on screen (overlay.c draws it): while R3 is held, and for a few seconds after a command. */
#ifndef SONGLIST_H
#define SONGLIST_H

#include <stdbool.h>

/* A command was given: keep the list on screen a while. */
void songlist_linger(void);
/* Each game frame, on the controller thread: what the list shows now. */
void songlist_frame(bool menu_open, int selected);

#endif
