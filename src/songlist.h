/* The song list on screen (overlay.c draws it): for a few seconds after switching songs. */
#ifndef SONGLIST_H
#define SONGLIST_H

#include <stdbool.h>

/* The selection changed: show the list a while. */
void songlist_linger(void);
/* A song started: take the list off the screen now. */
void songlist_hide(void);
/* Each game frame, on the controller thread: what the list shows now. */
void songlist_frame(int selected);

#endif
