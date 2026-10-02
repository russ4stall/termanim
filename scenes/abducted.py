"""
Abducted: the cyclist from rainy_ride, strapped to a table in a flying saucer.

The UFO finally got him. He lies on an examination table, still in his
helmet and rain jacket, strapped down at the chest, wrists and ankles and
breathing hard, while the ship hums around him: a heart monitor traces his
pulse (the tempo), a DNA scan spins on the console, stars and the Earth slide
past the porthole, and something with one eye floats in a specimen tank.

He is drawn from the same shaded shapes as in rainy_ride, laid on his back,
and every pose is rendered once and cached.

Every key is a short effect (well under a second), so they can be hit as
often as the music wants:

Keys:
    g   he struggles against the restraints (arms, then legs, then everything)
    a   the overhead scanner sweeps over him, x-raying him as it goes
    l   the restraints zap him
    f   a robot arm darts down and jabs him in the leg
    d   the alarm: the whole scene flashes one color (red, green, purple, white)
    s   the monitors glitch into alien static
    h   an alien pops up behind the table and blinks at him
    j   the thing in the tank throws itself at the glass
    up/down   tempo (his heart rate, on the monitor) +1 / -1 bpm
    Ctrl+C to stop

Usage:
    python3 play.py abducted                 # default 24 fps, 72 bpm
    python3 play.py abducted --bpm 120       # a racing heart
    python3 play.py abducted --mono          # no color
"""

import math
import os
import random
from dataclasses import dataclass, replace

from characters import alien, cyclist
from termanim import Canvas, Effect, Scene, action, rnd, run, smoothstep
from termanim.shading import Projector, add, lerp, mul, solve_joint, sub
from termanim.sprites import SpriteCache, cells_from_canvas, stamp

PALETTE = dict(cyclist.COLORS, **alien.COLORS, **{
    # the ship
    "hull": 237, "rib": 240, "seam": 235, "glow": 49, "glow_dk": 30, "light": 231,
    "table": 248, "table_dk": 242, "strap": 103,
    # out the porthole
    "star": 230, "star_dk": 60, "sea": 26, "land": 71,
    # screens and instruments
    "screen": 46, "screen_dk": 22, "warn": 214, "alarm": 196, "fluid": 23, "bubble": 123,
    # the local wildlife
    "critter": 205,
    # effects
    "xray": 159, "zap": 51,
})

DEFAULT_BPM = 72        # his heart rate
GLYPHS = "<>[]{}|/\\-+=~^vo:*"


def seg(cv, a, b, color, ch=None):
    """A line between two screen points (rows are about twice as tall as columns)."""
    (x0, y0), (x1, y1) = a, b
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
    c = ch or Projector.slope_char(x1 - x0, -(y1 - y0) * 2)
    for i in range(n + 1):
        cv.put(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, c, color)


def alien_text(n, seed):
    return "".join(" " if i % 5 == 4 else GLYPHS[int(rnd(i, seed) * len(GLYPHS))] for i in range(n))


# ---------------------------------------------------------------------------
# The cyclist (characters/cyclist.py), lying on his back: units with the
# table top at y = 0 and his head toward x = 0.
# ---------------------------------------------------------------------------

HEAD_LIFT = (0, 16, 32)     # degrees he lifts his head off the table, per Look.head


@dataclass(frozen=True)
class Look:
    """Everything that changes how he's drawn; the cached sprites are keyed on it."""
    breath: int = 0         # 1: chest filled
    head: int = 0           # index into HEAD_LIFT
    arms: int = 0           # 1: elbow wrenched up against the wrist strap
    legs: int = 0           # 1: near knee jerked up, 2: far knee
    arch: int = 0           # 1: back arched off the table


class Pose:
    """Where his joints are for a Look."""

    def __init__(self, look):
        arch = 1.4 * look.arch
        self.hip = (24.0, 2.7 + arch * 0.4)
        self.belly = (17.0, 2.9 + arch)
        self.shoulder = (10.0, 3.0 + arch * 0.5)
        self.chest = 2.8 + 0.3 * look.breath            # torso radius
        a = math.radians(HEAD_LIFT[look.head])
        self.up = (-math.cos(a), math.sin(a))           # toward the crown of his head
        self.fwd = (math.sin(a), math.cos(a))           # where his face points
        self.neck = add(self.shoulder, (-1.4, 1.4))
        self.head = add(self.neck, mul(self.up, 4.1))
        if look.arms:
            self.elbow, self.hand = (15.5, 6.4 + arch), (22.0, 3.0)
        else:
            self.elbow, self.hand = (16.5, 2.6 + arch * 0.8), (22.6, 2.4)
        self.legs = []                                  # (hip, knee, ankle, heel, toe), far leg first
        for far, raised in ((True, look.legs == 2), (False, look.legs == 1)):
            lift = 0.8 if far else 0.0
            hip = (24.0, 2.4 + lift + arch * 0.4)
            if raised:
                knee, ankle = (32.0, 7.2 + lift), (41.6, 2.4 + lift)
            else:
                knee, ankle = (34.0, 2.2 + lift), (43.5, 2.0 + lift)
            toe = add(ankle, (2.0 if far else 0.8, 3.0))
            self.legs.append((hip, knee, ankle, add(ankle, (-0.3, -0.6)), toe))
        self.knee, self.ankle = self.legs[1][1], self.legs[1][2]
        # where the straps go across him: chest, wrists, ankles
        self.straps = (14.0, self.hand[0] + 0.3, self.ankle[0] - 1.2)
        self.joints = cyclist.Joints(
            spine=(self.hip, self.belly, self.shoulder),
            neck=add(self.shoulder, (-0.5, 0.5)),
            head=self.head, fwd=self.fwd, up=self.up,
            shoulder=add(self.shoulder, (1.0, 0.4)), elbow=self.elbow, hand=self.hand,
            legs=tuple(self.legs), chest=self.chest)
        self.at = self.joints.at


def draw_rider_shape(cv, ax, ay, s, P):
    R = Projector(cv, ax, ay, s, materials=cyclist.MATERIALS)
    R.solids(cyclist.far_parts(P.joints))
    R.solids(cyclist.near_parts(P.joints))


def draw_bones(cv, ax, ay, s, P):
    """His skeleton, for the x-ray."""
    R = Projector(cv, ax, ay, s)
    R.arc(P.head, 2.6, 0, 2 * math.pi, "light")                                     # skull
    R.line(P.at(2.4, -0.9), P.at(0.8, -2.4), "light")                               # jaw
    sx, sy = R.to_screen(P.at(1.2, 0.2))
    cv.put(sx, sy, "@", "xray")                                                     # socket
    spine_a, spine_b = add(P.shoulder, (0, -1.4)), add(P.hip, (0, -1.4))
    R.line(P.neck, spine_a, "light")
    R.line(spine_a, spine_b, "light", "=")
    for i in range(4):                                                              # ribs
        base = lerp(spine_a, spine_b, 0.1 + 0.16 * i)
        R.line(base, add(base, (1.2, 3.2 + 0.2 * (P.chest - 2.8))), "light")
    R.arc(P.hip, 1.6, 0, 2 * math.pi, "light")                                      # pelvis
    R.line(P.shoulder, P.elbow, "light")
    R.line(P.elbow, P.hand, "light")
    for hip, knee, ankle, _, toe in P.legs:
        R.line(hip, knee, "light")
        R.line(knee, ankle, "light")
        R.line(ankle, toe, "light")
        kx, ky = R.to_screen(knee)
        cv.put(kx, ky, "o", "xray")


_SPRITES = SpriteCache()


def sprite_canvas(s):
    ax, ay = 4, int(7 * s) + 3
    return Canvas(int(50 * s) + 10, ay + 2), ax, ay


def rider_sprite(look, s):
    """(cells, the set of cells he covers), both relative to (head end, row above the table)."""
    def render():
        cv, ax, ay = sprite_canvas(s)
        draw_rider_shape(cv, ax, ay, s, Pose(look))
        cells = cells_from_canvas(cv, ax, ay)
        return cells, frozenset((dx, dy) for dx, dy, _, _ in cells)
    return _SPRITES.get(("body", look), s, render)


def bones_sprite(look, s):
    """His skeleton in this pose: relative cell -> (char, color)."""
    def render():
        cv, ax, ay = sprite_canvas(s)
        draw_bones(cv, ax, ay, s, Pose(look))
        return {(dx, dy): (ch, col) for dx, dy, ch, col in cells_from_canvas(cv, ax, ay)}
    return _SPRITES.get(("bones", look), s, render)


# ---------------------------------------------------------------------------
# Effects (started by the scene's actions, below)
# ---------------------------------------------------------------------------

class Struggle(Effect):
    """He fights the straps: each press is the next move (arms, legs, everything)."""
    layer = "rider"
    duration = 0.5
    MOVES = (
        ((0.0, dict(arms=1, head=1)), (0.12, dict(arms=1, head=2)),
         (0.25, dict(arms=1, head=1)), (0.38, dict(head=1))),
        ((0.0, dict(legs=1, head=1)), (0.12, dict(legs=2, head=1)),
         (0.25, dict(legs=1)), (0.38, dict(legs=2))),
        ((0.0, dict(arch=1, arms=1, head=1)), (0.12, dict(arch=1, arms=1, legs=1, head=2)),
         (0.25, dict(arch=1, legs=2, head=2)), (0.38, dict(arms=1, head=1))),
    )
    count = 0

    def __init__(self, t0):
        super().__init__(t0)
        self.moves = self.MOVES[Struggle.count % len(self.MOVES)]
        Struggle.count += 1
        self.seed = random.randrange(1, 1 << 30)

    def apply(self, f):
        age = self.age(f)
        if age < 0:
            return
        pose = {}
        for at, fields in self.moves:
            if age >= at:
                pose = fields
        f.look = replace(f.look, **pose)
        if age < 0.4:
            f.shake = (-1, 1)[int(age * 25) % 2]
        f.panic = max(f.panic, 1 - age / self.duration)
        f.eye, f.mouth = ">", "o"

    def draw(self, cv, f):
        age = self.age(f)
        if age < 0:
            return
        hx, hy = f.R.to_screen(add(f.pose.head, (0, 4.0)))
        if int(age * 16) % 2 == 0:                      # a flickering "!" over his head
            cv.put(hx + 1, hy - 1, "!", "warn")
        for i in range(4):                              # sweat flying off
            a = math.pi * (0.2 + 0.6 * rnd(i, self.seed))
            r = 1 + age * 14
            cv.put(hx + math.cos(a) * r * 1.6, hy + 1 - math.sin(a) * r * 0.6, "'", "xray")
        for ux in f.pose.straps:                        # the straps creak
            x = f.ox + f.shake + ux * f.s
            if rnd(ux, int(age * 20), self.seed) < 0.6:
                cv.put(x, f.strap_tops[ux] - 1, "~" if age < 0.25 else "-", "warn")


class Scan(Effect):
    """The overhead scanner sweeps a beam along him, x-raying him as it passes."""
    layer = "rider"
    duration = 0.6
    count = 0

    def __init__(self, t0):
        super().__init__(t0)
        self.backward = Scan.count % 2
        Scan.count += 1

    def apply(self, f):
        if self.age(f) >= 0:
            f.eye = "O"

    def draw(self, cv, f):
        age = self.age(f)
        if age < 0:
            return
        k = age / self.duration
        k = 1 - k if self.backward else k
        x0, x1 = f.ox - 3 * f.s, f.ox + 48 * f.s
        xs = x0 + (x1 - x0) * k
        ex, ey = f.scan_tip
        top = ey + 1
        for side in (-1, 1):                            # the edges of the beam
            a, b = (ex + side, top), (xs + side * 2, f.ty - 1)
            n = int(abs(b[1] - a[1])) + 1
            for i in range(n):
                p = lerp(a, b, i / n)
                if not f.inbody(int(round(p[0])), int(round(p[1]))):
                    cv.put(p[0], p[1], ":", "xray")
        bones = bones_sprite(f.look, f.s)
        half = max(2, int(2.5 * f.s))
        oy = f.ty - 1
        for x in range(int(xs) - half, int(xs) + half + 1):
            for y in range(top + 2, f.ty):
                if f.inbody(x, y):
                    bone = bones.get((x - f.body_x, y - oy))
                    cv.put(x, y, *(bone if bone else (".", "xray")))
                elif rnd(x, y, int(f.t * 30)) < 0.25:
                    cv.put(x, y, "|", "xray")
        for x in range(int(xs) - half, int(xs) + half + 1):     # where it hits the table
            cv.put(x, f.ty, "=", "light")


class Zap(Effect):
    """The straps crackle with electricity and he goes rigid."""
    layer = "rider"
    duration = 0.45

    def __init__(self, t0):
        super().__init__(t0)
        self.seed = random.randrange(1, 1 << 30)

    @staticmethod
    def visible(age):
        return age < 0.12 or 0.2 < age < 0.32 or 0.38 < age < 0.45

    def apply(self, f):
        age = self.age(f)
        if age < 0:
            return
        f.panic = max(f.panic, 1.0)
        if self.visible(age):
            f.look = replace(f.look, arch=1, arms=1, head=1)
            f.eye, f.mouth = "x", "o"
            f.shake = (-1, 1)[int(age * 40) % 2]

    def draw(self, cv, f):
        age = self.age(f)
        if age < 0 or not self.visible(age):
            return
        flick = int(age * 40)
        for dx, dy in f.body:                           # he lights up
            x, y = f.body_x + dx, f.ty - 1 + dy
            if rnd(dx, dy, flick) < 0.5:
                cv.recolor(x, y, "zap" if rnd(dx, dy, flick, 2) < 0.7 else "light")
        cols = [int(round(f.ox + f.shake + ux * f.s)) for ux in f.pose.straps]
        for i, x in enumerate(cols):                    # arcs up each strap and over him
            y = f.ty
            while y > f.strap_tops[f.pose.straps[i]] - 3:
                x += int(rnd(i, y, flick, self.seed) * 3) - 1
                cv.put(x, y, "/" if rnd(i, y, flick) < 0.5 else "\\", "zap")
                y -= 1
        for a, b in zip(cols, cols[1:]):                # and along the table between them
            for x in range(a, b):
                if rnd(x, flick, self.seed) < 0.6:
                    cv.put(x, f.ty, "~", "zap" if rnd(x, flick) < 0.6 else "light")


class Probe(Effect):
    """A robot arm darts down from the ceiling and jabs his leg."""
    layer = "fx"
    duration = 0.5
    HIT = (0.14, 0.3)       # the needle is in between these times

    def extension(self, age):
        if age < self.HIT[0]:
            return smoothstep(age / self.HIT[0])
        if age < self.HIT[1]:
            return 1.0
        return 1 - smoothstep((age - self.HIT[1]) / (self.duration - self.HIT[1]))

    def apply(self, f):
        age = self.age(f)
        if age < 0:
            return
        f.probe = max(f.probe, self.extension(age))
        if self.HIT[0] <= age < self.duration - 0.05:
            f.look = replace(f.look, arms=1, head=1)
            f.eye, f.mouth = "O", "o"
            f.panic = max(f.panic, 0.8)

    def draw(self, cv, f):
        age = self.age(f)
        if not self.HIT[0] <= age < self.HIT[1]:
            return
        x, y = f.probe_tip
        cv.put(x, y, "*", "light")
        rays = (("-", -1, 0), ("-", 1, 0), ("\\", -1, -1), ("/", 1, -1), ("/", -1, 1), ("\\", 1, 1))
        for i, (ch, dx, dy) in enumerate(rays):
            if (i + int(age * 30)) % 2:
                cv.put(x + dx * 2, y + dy, ch, "warn")


class Alarm(Effect):
    """The whole scene snaps to one color, then dissolves back."""
    layer = "top"
    duration = 0.35
    hold = 0.12
    colors = ("alarm", "glow", "alien_eye", "light")
    count = 0

    def __init__(self, t0):
        super().__init__(t0)
        self.color = self.colors[Alarm.count % len(self.colors)]
        Alarm.count += 1
        self.seed = random.randrange(1, 1 << 30)

    def draw(self, cv, f):
        age = self.age(f)
        if age < 0:
            return
        keep = 1.0 if age < self.hold else 1 - (age - self.hold) / (self.duration - self.hold)
        for y, (chars, colors) in enumerate(zip(cv.chars, cv.colors)):
            for x, ch in enumerate(chars):
                if ch != " " and (keep >= 1 or rnd(x, y, self.seed) < keep):
                    colors[x] = self.color


class Glitch(Effect):
    """The screens break up into alien static."""
    layer = None
    duration = 0.4

    def apply(self, f):
        if self.age(f) >= 0:
            f.glitch = True


class Peek(Effect):
    """An alien pops up from behind the table, blinks at him and ducks."""
    layer = "props"         # behind the table and him
    duration = 0.8

    def __init__(self, t0):
        super().__init__(t0)
        self.where = random.random()

    def draw(self, cv, f):
        age = self.age(f)
        if age < 0:
            return
        x0 = int(f.tl + 2 + self.where * (f.tr - f.tl - alien.WIDTH - 4))
        _, body = rider_sprite(f.look, f.s)
        cols = range(x0 + alien.EYES[0] - f.ox, x0 + alien.EYES[1] - f.ox)
        above = min([dy for dx, dy in body if dx in cols] or [0])
        up = f.ty - 1 + above - alien.EYE_ROW - 2       # eyes just over him
        if age < 0.12:
            k = smoothstep(age / 0.12)
        elif age < 0.65:
            k = 1.0
        else:
            k = 1 - smoothstep((age - 0.65) / 0.15)
        top = int(round(f.ty + (up - f.ty) * k))
        alien.draw(cv, x0, top, blink=0.38 < age < 0.48, neck=8, bottom=f.ty)


class Thump(Effect):
    """The thing in the tank hurls itself at the glass."""
    layer = None            # sets f.thump, which the tank reads
    duration = 0.5

    def apply(self, f):
        age = self.age(f)
        if age >= 0:
            f.thump = max(f.thump, 1 - age / self.duration)


# ---------------------------------------------------------------------------
# The heart monitor's trace
# ---------------------------------------------------------------------------

ECG = ((0.08, 0), (0.14, 1), (0.18, 0), (0.20, -1), (0.24, 3), (0.27, -2), (0.40, 0), (0.52, 1))
ECG_STEP = 0.05         # seconds per column of trace
PANIC_TRACE = 0.6       # seconds of wild trace after a fright


def ecg(phase):
    for end, v in ECG:
        if phase < end:
            return v
    return 0


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------

class Abducted(Scene):
    name = "abducted"
    description = "The rainy_ride cyclist, strapped to a table in a flying saucer"
    palette = PALETTE
    min_size = (72, 24)
    default_bpm = DEFAULT_BPM
    bpm_help = "his heart rate"
    loading_message = "Calibrating the probes..."
    goodbye = "Back on Earth. Nobody believes him. \U0001F47D"
    layers = [
        "room",         # ceiling, ribs, floor, porthole
        "props",        # heart monitor, console, scanner, specimen tank
        "table",        # the examination table
        "rider",        # him, and the straps
        "fx",           # the robot arm
        "top",          # over everything
    ]

    def __init__(self, args=None):
        super().__init__(args)
        self.frights = []               # when he got a fright (for the heart monitor)

    def layout(self, f):
        w, h = f.w, f.h
        f.s = s = max(0.8, min(2.4, min(w / 82.0, h / 24.0)))
        f.floor = h - max(3, int(h * 0.12))
        f.ty = f.floor - max(6, int(h * 0.26))          # the table top's row
        f.ox = int(w * 0.46) - int(23 * s)              # his head end (unit x = 0)
        f.tl, f.tr = f.ox - 3, f.ox + int(47 * s) + 1
        f.ceil = [int(round(1 + 2.5 * ((x - w / 2) / (w / 2)) ** 2)) for x in range(w)]
        f.scan_x = f.ox + int(15 * s)
        f.scan_y = max(f.ceil[f.scan_x] + 4, f.ty - int(6 * s) - 4)    # scanner's bottom row
        f.scan_tip = (f.scan_x, f.scan_y)
        f.arm_base = (f.ox + int(36 * s), f.ceil[min(w - 1, f.ox + int(36 * s))] + 1)
        # breathing: in for two beats, out for two
        f.look = Look(breath=int(f.beats / 2) % 2)
        # things effects may change for this frame only (in Effect.apply)
        f.eye = None                    # None: open (or blinking)
        f.mouth = None
        f.shake = 0                     # columns he's jolted sideways
        f.panic = 0.0                   # 0 calm .. 1 struggling: the strap lights
        f.probe = 0.0                   # how far the robot arm reaches
        f.glitch = False
        f.thump = 0.0

    def warm_up(self, f):
        """Render every pose up front, so the first struggle doesn't stutter."""
        poses = [{}, dict(arch=1, arms=1, head=1)]
        poses += [fields for moves in Struggle.MOVES for _, fields in moves]
        for fields in poses:
            for breath in (0, 1):
                rider_sprite(Look(breath=breath, **fields), f.s)

    def prepare_still(self, t):
        for key in os.environ.get("KEYS", ""):          # KEYS=ga: press g and a just before t
            self.press(key, t - 0.2)

    def update(self, t):
        super().update(t)
        self.frights = [p for p in self.frights if t - p < 30]

    # --- layers ------------------------------------------------------------

    def draw_room(self, cv, f):
        w, ceil = cv.w, f.ceil
        mid = (ceil[w // 2] + f.floor) // 2
        for x in range(w):                              # wall ribs and a panel seam
            if x % 18 == 9:
                for y in range(ceil[x] + 1, f.floor):
                    cv.put(x, y, ":" if y % 4 == 0 else "|", "rib")
            elif x % 3:
                cv.put(x, mid, "-", "seam")
        for x in range(w):                              # the domed ceiling
            y = ceil[x]
            nxt = ceil[min(w - 1, x + 1)]
            cv.put(x, y, "/" if nxt < y else "\\" if nxt > y else "_", "rib")
            for yy in range(y):
                if rnd(x, yy, 7) < 0.12:
                    cv.put(x, yy, ".", "hull")
            if x % 7 == 3:                              # a chasing strip of lights
                lit = (x // 7 - int(f.beats * 4)) % 5 == 0
                cv.put(x, y + 1, "v", "light" if lit else "glow_dk")
        cv.text(0, f.floor, "=" * w, "rib")             # the floor, in perspective
        vx, vy = w / 2, f.floor - (cv.h - f.floor) * 3
        for y in range(f.floor + 1, cv.h):
            d = y - vy
            for x in range(w):
                u = (x - vx) / d * 1.6
                if abs(u - round(u)) < 0.5 * 1.6 / d:
                    n = round(u)
                    cv.put(x, y, "|" if n == 0 else "/" if n < 0 else "\\", "seam")
        self.draw_porthole(cv, f)

    def draw_porthole(self, cv, f):
        left, right = f.scan_x + 6, cv.w - 14
        rx = min(12, (right - left) / 2 - 1)
        if rx < 5:
            return
        px = (left + right) / 2
        top = f.ceil[int(px)] + 2
        ry = max(2.0, min(rx * 0.42, (f.ty - 4 - top) / 2))
        py = top + ry
        # the Earth, low in the window, turning
        ex, ey, er = px + rx * 0.35, py + ry * 0.9, ry * 1.1
        for y in range(int(py - ry), int(py + ry) + 1):
            for x in range(int(px - rx), int(px + rx) + 1):
                if ((x - px) / rx) ** 2 + ((y - py) / ry) ** 2 >= 0.85:
                    continue
                v = (y - ey) / er
                u = (x - ex) / (er * 2)
                if u * u + v * v < 1:
                    lon = math.asin(max(-1, min(1, u / math.sqrt(1 - v * v + 1e-9)))) + f.t * 0.15
                    land = rnd(int(lon * 4), int(v * 3), 9) < 0.45
                    cv.put(x, y, "#" if land else "~", "land" if land else "sea")
                elif rnd(x + int(f.t * 3), y, 1) < 0.06:
                    cv.put(x, y, ".", "star_dk")
                elif rnd(x + int(f.t * 9), y, 2) < 0.025:
                    cv.put(x, y, "*", "star")
                else:
                    cv.put(x, y, " ")
        steps = int(rx * 6)
        for i in range(steps):                          # the rim
            a = 2 * math.pi * i / steps
            x, y = px + (rx + 0.6) * math.cos(a), py + (ry + 0.5) * math.sin(a)
            ch = Projector.slope_char(-math.sin(a) * rx, -math.cos(a) * ry * 2)
            cv.put(x, y, ch, "metal")
        for i in range(8):                              # rivets
            a = 2 * math.pi * (i + 0.5) / 8
            cv.put(px + (rx + 2) * math.cos(a), py + (ry + 1) * math.sin(a), "o", "table_dk")

    def draw_props(self, cv, f):
        self.draw_monitor(cv, f)
        self.draw_console(cv, f)
        self.draw_scanner(cv, f)
        self.draw_tank(cv, f)

    def box(self, cv, x0, y0, x1, y1, color):
        for y in range(y0 + 1, y1):                     # blank out the wall behind it
            for x in range(x0 + 1, x1):
                cv.put(x, y, " ")
        for x in range(x0 + 1, x1):
            cv.put(x, y0, "-", color)
            cv.put(x, y1, "-", color)
        for y in range(y0 + 1, y1):
            cv.put(x0, y, "|", color)
            cv.put(x1, y, "|", color)
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            cv.put(x, y, "+", color)

    def static(self, cv, f, x0, y0, x1, y1):
        """Alien glyphs flickering over a screen (the glitch)."""
        n = int(f.t * 20)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                r = rnd(x, y, n)
                if r < 0.6:
                    color = ("screen", "alarm", "glow", "light")[int(rnd(x, y, n, 3) * 4)]
                    cv.put(x, y, GLYPHS[int(r / 0.6 * len(GLYPHS))], color)

    def draw_monitor(self, cv, f):
        """The heart monitor, hanging from the ceiling at the left."""
        x0, x1 = 2, min(36, f.scan_x - 6)
        y0 = f.ceil[x0] + 1
        y1 = min(y0 + 10, f.ty - int(6 * f.s) - 3)    # clear of his head when he lifts it
        if x1 - x0 < 10 or y1 - y0 < 5:
            return
        for x in (x0 + 2, x1 - 2):
            for y in range(f.ceil[x] + 1, y0):
                cv.put(x, y, "|", "table_dk")
        self.box(cv, x0, y0, x1, y1, "table_dk")
        ix0, ix1, iy0, iy1 = x0 + 1, x1 - 1, y0 + 1, y1 - 1
        if f.glitch:
            self.static(cv, f, ix0, iy0, ix1, iy1)
            return
        rows = iy1 - iy0                                # for the trace (the last row's the readout)
        if rows >= 7:
            cv.text(ix0 + 1, iy0, alien_text(min(14, ix1 - ix0 - 1), 5), "screen_dk")
            rows -= 1
        down = 2 if rows >= 6 else 1                    # rows below the baseline, and above it
        up = min(3, rows - 1 - down)
        base = iy1 - 1 - down
        width = ix1 - ix0 + 1
        prev = None
        for c in range(width):
            tc = f.t - (width - 1 - c) * ECG_STEP
            if any(0 <= tc - p < PANIC_TRACE for p in self.frights):
                v = int(rnd(int(tc / ECG_STEP), 77) * (up + down + 1)) - down
            else:
                v = max((ecg(self.tempo.beats(tc + j * ECG_STEP / 4) % 1.0) for j in range(4)), key=abs)
                v = max(-down, min(up, v if v < 3 else up))
            color = "light" if c >= width - 2 else "screen"
            if prev is not None and abs(v - prev) > 1:
                for y in range(base - max(v, prev) + 1, base - min(v, prev)):
                    cv.put(ix0 + c, y, "|", color)
            cv.put(ix0 + c, base - v, "-" if abs(v) < 2 else "|", color)
            prev = v
        beat = self.tempo.beats(f.t) % 1.0
        cv.text(ix0 + 1, iy1, "HR %d" % round(self.tempo.bpm), "screen")
        heart = "!!" if f.panic > 0 else "<3"
        cv.text(ix1 - 2, iy1, heart, "alarm" if beat < 0.2 or f.panic > 0 else "screen_dk")

    def draw_console(self, cv, f):
        """A console by his head: a spinning DNA scan and blinking buttons."""
        x0, x1 = 1, f.tl - 3
        y0, y1 = f.ty - 1, f.floor - 1
        if x1 - x0 < 8 or y1 - y0 < 5:
            return
        self.box(cv, x0, y0, x1, y1, "table_dk")
        sx0, sx1, sy0, sy1 = x0 + 2, x1 - 2, y0 + 1, min(y0 + 5, y1 - 2)
        if f.glitch:
            self.static(cv, f, sx0, sy0, sx1, sy1)
        else:
            mid, amp = (sy0 + sy1) / 2, (sy1 - sy0) / 2
            for x in range(sx0, sx1 + 1):
                ph = x * 0.55 + f.t * 3
                a, b = mid + amp * math.sin(ph), mid - amp * math.sin(ph)
                if x % 2 == 0:
                    for y in range(int(round(min(a, b))) + 1, int(round(max(a, b)))):
                        cv.put(x, y, ":", "screen_dk")
                front = math.cos(ph) > 0
                cv.put(x, a, "o" if front else ".", "glow" if front else "glow_dk")
                cv.put(x, b, "." if front else "o", "glow_dk" if front else "glow")
        for y in range(sy1 + 2, y1, 2):                 # buttons
            for i, x in enumerate(range(x0 + 2, x1 - 1, 2)):
                r = rnd(i, y, int(f.beats * 2))
                cv.put(x, y, "o", ("alarm", "warn", "glow", "screen_dk")[int(r * 4)])

    def draw_scanner(self, cv, f):
        x, y = f.scan_x, f.scan_y
        for yy in range(f.ceil[x] + 1, y - 1):
            cv.text(x - 1, yy, "||", "table_dk")
        cv.text(x - 4, y - 1, "/======\\", "metal")
        cv.text(x - 4, y, "\\", "metal")
        cv.text(x + 3, y, "/", "metal")
        for i in range(6):
            lit = (i + int(f.beats * 2)) % 3 == 0
            cv.put(x - 3 + i, y, "o", "glow" if lit else "glow_dk")
        if rnd(int(f.t * 6), 3) < 0.3:                  # an idle shimmer below it
            cv.put(x - 1 + int(rnd(int(f.t * 6), 4) * 3), y + 1, ".", "glow_dk")

    def draw_tank(self, cv, f):
        """A specimen tank with something in it."""
        tw = 9
        x0, x1 = cv.w - tw - 2, cv.w - 3
        y0, y1 = max(f.ceil[x0] + 3, f.ty - 7), f.floor - 1
        k = f.thump
        for x in (x0 + 2, x1 - 2):                      # pipes to the ceiling
            for y in range(f.ceil[x] + 1, y0):
                cv.put(x, y, "|", "table_dk")
        cv.text(x0, y0, "[" + "=" * (tw - 2) + "]", "metal")
        cv.text(x0, y1, "[" + "=" * (tw - 2) + "]", "metal")
        glass = "light" if k > 0.6 else "glow_dk"
        for y in range(y0 + 1, y1):
            cv.put(x0, y, "|", glass)
            cv.put(x1, y, "|", glass)
        for x in range(x0 + 1, x1):                     # the fluid's surface
            cv.put(x, y0 + 1, "~" if (x + int(f.t * 3)) % 3 else "-", "fluid")
        height = y1 - y0 - 2
        for i in range(5 + int(k * 8)):                 # bubbles (more when it thumps)
            speed = 2 + rnd(i, 2) * 3 + k * 10
            y = y1 - 1 - (rnd(i, 3) * height + f.t * speed) % height
            x = x0 + 1 + int(rnd(i, 1, int((f.t * speed + rnd(i, 3) * height) / height)) * (tw - 2))
            cv.put(x, y, "o" if rnd(i, 4) < 0.4 else ".", "bubble")
        cx = (x0 + x1) // 2
        cy = int(round((y0 + y1) / 2 + math.sin(f.t * 1.7)))
        if k > 0:                                       # pressed to the glass
            jolt = (-1, 1)[int(f.t * 30) % 2] if k > 0.5 else 0
            body = (".---.", "( O )", "\\\\|//")
            for r, row in enumerate(body):
                cv.text(cx - 2 + jolt, cy - 1 + r, row, "critter")
            if k > 0.6:
                for dx, dy, ch in ((-3, -1, "\\"), (3, -1, "/"), (-3, 1, "/"), (3, 1, "\\")):
                    cv.put(cx + dx, cy + dy, ch, "light")
        else:
            legs = "/|\\" if int(f.t * 4) % 2 else "\\|/"
            eye = "-" if (f.t % 5.3) < 0.15 else "o"
            for r, row in enumerate((".-.", "(" + eye + ")", legs)):
                cv.text(cx - 1, cy - 1 + r, row, "critter")

    def draw_table(self, cv, f):
        ty, tl, tr = f.ty, f.tl, f.tr
        cv.text(tl, ty, "[" + "=" * (tr - tl - 1) + "]", "table")
        cv.put(tl + 1, ty + 1, "\\", "table_dk")
        cv.put(tr - 1, ty + 1, "/", "table_dk")
        for x in range(tl + 2, tr - 1):                 # running lights under the edge
            lit = (x - int(f.t * 12)) % 8 == 0
            cv.put(x, ty + 1, "." if lit else "_", "glow" if lit else "table_dk")
        cx = (tl + tr) // 2
        pulse = int(f.beats * 2) % 2
        for y in range(ty + 2, f.floor - 1):
            cv.put(cx - 2, y, "|", "table")
            cv.put(cx + 2, y, "|", "table")
            core = (y - int(f.t * 8)) % 3 == 0
            cv.text(cx - 1, y, ":::" if core else " : ", "glow" if pulse else "glow_dk")
        cv.text(cx - 5, f.floor - 1, "/=========\\", "table_dk")

    def draw_rider(self, cv, f):
        """The cached sprite, then what changes every frame: eye, mouth, straps."""
        cells, body = rider_sprite(f.look, f.s)
        ox, oy = f.ox + f.shake, f.ty - 1
        stamp(cv, cells, ox, oy)
        f.body, f.body_x = body, ox
        f.inbody = lambda x, y: (x - ox, y - oy) in body
        P = f.pose = Pose(f.look)
        R = f.R = Projector(cv, ox, oy, f.s)
        # the eye: open, blinking now and then, or whatever an effect makes it
        eye = f.eye or ("-" if f.t % 3.7 < 0.13 else "o")
        cyclist.draw_face(cv, R, P.joints, eye, f.mouth or "-")
        # the straps, wrapped over him, with a light on each buckle
        f.strap_tops = {}
        width = 2 if f.s >= 1.4 else 1
        for ux in P.straps:
            col = int(round(ox + ux * f.s))
            top = oy
            for x in range(col, col + width):
                y = oy
                while f.inbody(x, y):
                    cv.put(x, y, "#", "strap")
                    y -= 1
                top = min(top, y + 1)
                light = "alarm" if f.panic > 0 and int(f.t * 16) % 2 else "glow"
                cv.put(x, f.ty, "o", light)
            f.strap_tops[ux] = top

    def draw_fx(self, cv, f):
        """The robot arm: folded up under the ceiling, or reaching down to jab him."""
        to_u = lambda p: (p[0], -p[1] * 2)              # screen -> units (y up)
        to_s = lambda p: (p[0], -p[1] / 2)
        base = to_u(f.arm_base)
        P = f.pose
        target = to_u(f.R.to_screen(add(lerp(P.legs[1][0], P.legs[1][1], 0.45), (0, 2.1))))
        reach = math.hypot(*sub(target, base))
        bone = reach * 0.5
        # reaching: the wrist sits right above the target, the needle points down
        wrist = add(target, (0, 3))
        elbow = max((solve_joint(base, wrist, bone, bone, bend) for bend in (1, -1)),
                    key=lambda p: p[0])                 # the elbow sticks out to the right
        reach_angles = (math.atan2(elbow[1] - base[1], elbow[0] - base[0]),
                        math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0]))
        rest_angles = (math.radians(-12), math.radians(-160))   # folded up
        k = f.probe
        a1, a2 = (r + (g - r) * k for r, g in zip(rest_angles, reach_angles))
        elbow = add(base, (bone * math.cos(a1), bone * math.sin(a1)))
        wrist = add(elbow, (bone * math.cos(a2), bone * math.sin(a2)))
        tip = add(wrist, (0, -3))
        base, elbow, wrist, tip = map(to_s, (base, elbow, wrist, tip))
        f.probe_tip = tip
        seg(cv, base, elbow, "metal")
        seg(cv, elbow, wrist, "metal")
        seg(cv, wrist, tip, "light", "|")
        cv.put(wrist[0], wrist[1], "V", "table_dk")
        cv.put(elbow[0], elbow[1], "o", "glow")
        cv.text(int(base[0]) - 1, int(base[1]), "[o]", "table_dk")

    def draw_top(self, cv, f):
        """Nothing of its own: the alarm flash draws here, over everything."""

    # --- actions -----------------------------------------------------------

    @action("struggle", keys="g")
    def struggle(self, t):
        self.frights.append(t)
        self.add_effect(Struggle(t))

    @action("scan", keys="a")
    def scan(self, t):
        self.add_effect(Scan(t))

    @action("zap", keys="l")
    def zap(self, t):
        self.frights.append(t)
        self.add_effect(Zap(t))

    @action("probe", keys="f")
    def probe(self, t):
        self.frights.append(t)
        self.add_effect(Probe(t))

    @action("alarm", keys="d")
    def alarm(self, t):
        self.add_effect(Alarm(t))

    @action("glitch", keys="s")
    def glitch(self, t):
        self.add_effect(Glitch(t))

    @action("peek", keys="h")
    def peek(self, t):
        self.add_effect(Peek(t))

    @action("thump", keys="j")
    def thump(self, t):
        self.add_effect(Thump(t))


if __name__ == "__main__":
    run(Abducted)
