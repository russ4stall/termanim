"""The character grid every frame is drawn into, and turning it into output."""

from .terminal import RESET


class Canvas:
    """A grid of characters, each with a color name (a key of the scene's
    palette, or None for the default color)."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.chars = [[" "] * w for _ in range(h)]
        self.colors = [[None] * w for _ in range(h)]

    def put(self, x, y, ch, color=None):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.chars[y][x] = ch
            self.colors[y][x] = color

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.chars[y][x]
        return None

    def recolor(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.colors[y][x] = color

    def text(self, x, y, s, color):
        for i, ch in enumerate(s):
            if ch != " ":
                self.put(x + i, y, ch, color)

    def render(self, codes):
        """The whole canvas as text. `codes` maps color names to escape codes
        (see terminal.color_codes); None draws without color."""
        if codes is None:
            return "\r\n".join("".join(row) for row in self.chars) + RESET
        out = []
        prev = None
        for chars, colors in zip(self.chars, self.colors):
            parts = []
            run = 0                         # start of the current same-color run
            for x, col in enumerate(colors):
                if col != prev and chars[x] != " ":
                    parts.append("".join(chars[run:x]))
                    parts.append(codes[col])
                    prev, run = col, x
            parts.append("".join(chars[run:]))
            out.append("".join(parts))
        return "\r\n".join(out) + RESET

    def render_diff(self, prev, codes):
        """Only the cells that changed since `prev`. Over SSH this sends a
        fraction of what a full redraw does. Runs of changed cells are grouped
        by color so each color code is sent once, not once per raindrop."""
        mono = codes is None
        runs = {}                           # color (or "mixed") -> [(y, x0, x1)]
        for y in range(self.h):
            chars, colors = self.chars[y], self.colors[y]
            pchars, pcolors = prev.chars[y], prev.colors[y]
            if chars == pchars and (mono or colors == pcolors):
                continue
            changed = [x for x in range(self.w)
                       if chars[x] != pchars[x]
                       or (not mono and chars[x] != " " and colors[x] != pcolors[x])]
            i = 0
            while i < len(changed):
                # merge changes separated by short gaps: rewriting a few
                # unchanged cells is cheaper than another cursor jump
                j = i
                while j + 1 < len(changed) and changed[j + 1] - changed[j] <= 3:
                    j += 1
                x0, x1 = changed[i], changed[j]
                used = {colors[x] for x in range(x0, x1 + 1) if chars[x] != " "}
                key = "mixed" if len(used) > 1 and not mono else (used.pop() if used and not mono else "")
                runs.setdefault(key, []).append((y, x0, x1))
                i = j + 1

        out = []
        cur = None                          # color in effect (None = reset)
        at = None                           # cursor position after the last write
        for key, group in runs.items():
            if key not in ("", "mixed") and key != cur:
                cur = key
                out.append(codes[cur])
            for y, x0, x1 in group:
                if at and at[0] == y and at[1] <= x0:
                    if x0 > at[1]:
                        out.append("\033[%dC" % (x0 - at[1]))     # skip right
                else:
                    out.append("\033[%d;%dH" % (y + 1, x0 + 1))
                chars, colors = self.chars[y], self.colors[y]
                if key == "mixed":
                    for x in range(x0, x1 + 1):
                        if chars[x] != " " and colors[x] != cur:
                            cur = colors[x]
                            out.append(codes[cur])
                        out.append(chars[x])
                else:
                    out.append("".join(chars[x0:x1 + 1]))
                at = (y, x1 + 1)
        if cur is not None:
            out.append(RESET)
        return "".join(out)
