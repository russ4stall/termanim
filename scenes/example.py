"""
Starry night: a minimal scene to copy when starting a new one.

Stars drift past and twinkle, a lighthouse beam sweeps once per beat.

Keys:
    s   a shooting star
    up/down   tempo +1 / -1 bpm
"""

import math
import random

from termanim import Effect, Scene, action, rnd, run


class ShootingStar(Effect):
    """A streak across the sky, from a random spot, down and to the left."""
    layer = "sky"           # drawn right after the sky layer, behind the lighthouse
    duration = 0.6

    def __init__(self, t0):
        super().__init__(t0)
        self.x, self.y = random.random(), random.random() * 0.3     # fractions of the screen

    def draw(self, cv, f):
        k = self.age(f) / self.duration
        x, y = self.x * f.w + 20 - 40 * k, self.y * f.h + 10 * k
        for d in range(6):                          # head, then a fading tail
            cv.put(x + d * 2, y - d * 0.5, "*" if d == 0 else "-", "star" if d < 3 else "dim")


class StarryNight(Scene):
    name = "example"
    description = "Starry night: a minimal example scene"
    palette = {"star": 230, "dim": 60, "sea": 24, "tower": 250, "beam": 229}
    min_size = (40, 12)
    layers = ["sky", "sea", "lighthouse"]

    def layout(self, f):
        f.sea = int(f.h * 0.75)                     # first row of the sea
        f.tower = int(f.w * 0.75)                   # the lighthouse's column

    def draw_sky(self, cv, f):
        drift = int(f.t * 2)                        # stars slide slowly left
        for y in range(f.sea):
            for x in range(f.w):
                if rnd(x + drift, y) < 0.02:
                    twinkle = rnd(x + drift, y, int(f.t * 4)) < 0.2
                    cv.put(x, y, "+" if twinkle else ".", "star" if twinkle else "dim")

    def draw_sea(self, cv, f):
        for y in range(f.sea, f.h):
            for x in range(f.w):
                if rnd(x + int(f.t * 6) * (y - f.sea + 1), y, 3) < 0.3:
                    cv.put(x, y, "~", "sea")

    def draw_lighthouse(self, cv, f):
        top = f.sea - 6
        for y in range(top, f.sea):
            cv.text(f.tower - 1, y, "|#|", "tower")
        # the beam goes round once per beat, so it keeps time with --bpm
        angle = f.beats * 2 * math.pi
        reach = int(f.w * 0.5 * abs(math.cos(angle)))
        side = 1 if math.cos(angle) > 0 else -1
        for d in range(2, reach):
            cv.put(f.tower + side * d, top - 1 + d // 12, "=", "beam")
        cv.put(f.tower, top - 1, "@", "beam")

    @action("shooting_star", keys="s")
    def shooting_star(self, t):
        self.add_effect(ShootingStar(t))


if __name__ == "__main__":
    run(StarryNight)
