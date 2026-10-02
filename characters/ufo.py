"""
The flying saucer: a domed hull with someone peering out, running lights
chasing round the rim, a searchlight and a tractor beam.

It's drawn with its top-left corner at (x, y) in screen cells; where it
flies and whom it takes is up to the scene:

    ufo.draw_searchlight(cv, x, y, sweep, t, seed)     # while it hunts
    ufo.draw_beam(cv, x, y, ground, t)                 # while it abducts
    ufo.draw_saucer(cv, x, y, t)                       # the ship, over its beams
"""

from termanim import rnd

# Its colors (xterm-256 indices), to merge into a scene's palette.
COLORS = {
    "ufo_hull": 250, "ufo_dome": 117, "ufo_pilot": 43, "ufo_beam": 43, "ufo_glint": 117,
    "ufo_amber": 229, "ufo_red": 160, "ufo_white": 231,
}

SHIP = ("    ___    ",
        " __/o o\\__ ",
        "(_=_=_=_=_)")
PAINT = ("    ddd    ",      # d dome, e pilot's eyes, m metal hull, l running light
         " mmde edmm ",
         "mmlmlmlmlmm")
INKS = {"d": "ufo_dome", "e": "ufo_pilot", "m": "ufo_hull"}
LIGHTS = ("ufo_amber", "ufo_red", "ufo_white")
WIDTH, HEIGHT = len(SHIP[0]), len(SHIP)


def beam_source(x, y):
    """The cell under the middle of the hull, where its beams come from."""
    return x + 5, y + 3


def draw_saucer(cv, x, y, t):
    for r, (row, paint) in enumerate(zip(SHIP, PAINT)):
        for c, (ch, ink) in enumerate(zip(row, paint)):
            if ch == " ":
                continue
            if ink == "l":                              # running lights chase round
                color = LIGHTS[(c // 2 + int(t * 8)) % len(LIGHTS)]
            else:
                color = INKS[ink]
            cv.put(x + c, y + r, ch, color)


def draw_searchlight(cv, x, y, sweep, t, seed):
    """A flickering searchlight below the ship; sweep (-1..1) swings it side to side."""
    cx, bottom = beam_source(x, y)
    for d in range(1, 9):
        if rnd(d, int(t * 20), seed) < 0.7:
            cv.put(cx + d * sweep * 1.3, bottom + d - 1, "." if d > 2 else ":", "ufo_amber")


def draw_beam(cv, x, y, ground, t, put=None):
    """The tractor beam, widening down to row `ground`. `put` (default cv.put)
    lets a scene hide parts of it, e.g. behind buildings."""
    put = put or cv.put
    cx, bottom = beam_source(x, y)
    for row in range(bottom, ground + 1):
        half = 1 + (row - bottom) * 0.35
        put(cx - half, row, "/", "ufo_beam")
        put(cx + half, row, "\\", "ufo_beam")
        for xx in range(int(cx - half) + 1, int(cx + half)):
            if rnd(xx, row, int(t * 15)) < 0.3:
                put(xx, row, ":", "ufo_glint")
