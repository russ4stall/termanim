"""Caching pre-rendered drawings, so slow ones (shaded figures) are drawn
once and then just stamped onto each frame. Keeps slow machines smooth."""


class SpriteCache:
    """Sprites by key, for one scale at a time: when the scale changes (the
    terminal was resized) the old ones are stale and are dropped.
    Anything that changes a drawing must be in its key, or the sprite will be
    stuck at its first-seen state."""

    def __init__(self):
        self._sprites = {}
        self._scale = None

    def get(self, key, scale, render):
        """The sprite for key at this scale, calling render() the first time."""
        if scale != self._scale:
            self._sprites.clear()
            self._scale = scale
        if key not in self._sprites:
            self._sprites[key] = render()
        return self._sprites[key]


def cells_from_canvas(cv, ax, ay):
    """A canvas's drawn cells as (dx, dy, char, color) relative to (ax, ay)."""
    return [(x - ax, y - ay, ch, cv.colors[y][x])
            for y, row in enumerate(cv.chars)
            for x, ch in enumerate(row) if ch != " "]


def stamp(cv, cells, x0, y0):
    """Draw sprite cells with their anchor at (x0, y0)."""
    w, h, chars, colors = cv.w, cv.h, cv.chars, cv.colors
    for dx, dy, ch, col in cells:
        x, y = x0 + dx, y0 + dy
        if 0 <= x < w and 0 <= y < h:
            chars[y][x] = ch
            colors[y][x] = col
