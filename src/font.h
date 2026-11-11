/* 8x8 bitmap font for the song list (font.c). */
#ifndef FONT_H
#define FONT_H

#include <stdint.h>

#define FONT_FIRST 33 /* '!'; a space and anything outside the font draw nothing */
#define FONT_COUNT 94 /* up to '~' */
#define FONT_W     8
#define FONT_H     8

/* row bits, MSB = leftmost pixel */
extern const uint8_t font_8x8[FONT_COUNT][FONT_H];

#endif
