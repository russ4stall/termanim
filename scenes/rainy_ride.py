"""
Rainy ride: a cartoon ASCII animation for the terminal.

A cyclist in a rain jacket pedals endlessly through a rainy city night.
The street, lamps and skyline scroll past at different speeds, the rain
splashes on the road and sparkles under the street lamps, and his
headlight cuts a beam through the downpour.

The rider is drawn from shaded shapes (torso, backpack, helmeted head,
arms, legs) so he looks solid. His legs follow the rotating pedals.
The bike has spoked wheels and a running chain.

The shaded rider and bike are rendered once per pedal position and cached,
so each frame only stamps a ready-made sprite.

Keys:
    l   a lightning strike somewhere over the city
    a   the street lamps flash
    s   half the building windows switch on or off, all at once
    d   the whole scene flashes one color (red, orange, teal, white in turn)
    f   a car speeds past in the near lane
    g   the rider pops a wheelie
    h   a gust of wind blows the rain sideways
    j   a UFO flies in, searches the city and abducts someone (on a roof, in
        front of or behind a building, or scrolling in from the side)
    up/down   tempo +1 / -1 bpm (shown bottom right)
    Ctrl+C to stop

The rider himself is characters/cyclist.py (shared with other scenes); this
scene poses him on the bike. New poses go in Look, so the cached sprites stay
correct.

Usage:
    python3 play.py rainy_ride               # default 24 fps, 84 bpm
    python3 play.py rainy_ride --bpm 120     # pedal faster (one revolution per beat)
    python3 play.py rainy_ride --mono        # no color
    python3 play.py rainy_ride --bench 200   # render 200 frames off-screen, print fps
"""

import bisect
import math
import os
import random
from dataclasses import dataclass, replace

from characters import cyclist, ufo
from characters.cyclist import SHIN, THIGH, Joints
from termanim import Canvas, Effect, Scene, action, rnd, run, smoothstep
from termanim.shading import Projector, add, polar, solve_joint
from termanim.sprites import SpriteCache, cells_from_canvas, stamp

# Every color in the animation (xterm-256 indices). Kept to 24 or fewer.
PALETTE = dict(cyclist.COLORS, **ufo.COLORS, **{
    # the city
    "cloud": 60, "bldg": 239, "win": 221, "windark": 237, "lamp": 229, "glow": 136,
    "rain": 117, "rain2": 68, "road": 238, "lane": 252, "curb": 245, "puddle": 31,
    # his bike
    "frame": 43, "tire": 240,
    # the storm
    "bolt": 231,
})
assert len(set(PALETTE.values())) <= 24   # characters may share colors under their own names

SCROLL_SPEED = 24       # columns per second the street slides by
DEFAULT_BPM = 84        # pedal revolutions per minute; the street speed scales with it
COLS_PER_REV = SCROLL_SPEED * 60.0 / DEFAULT_BPM    # street columns per pedal revolution
PHASES = 24             # cached rider poses per pedal revolution
LIFT_ANGLES = (0, 8, 16)  # wheelie: degrees the front wheel is lifted, per Look.lift

# ---------------------------------------------------------------------------
# The bike and rider live in units (see termanim.shading), with the rear
# wheel's contact patch at the origin.
# ---------------------------------------------------------------------------

WHEEL_R = 7.0
REAR_HUB = (0.0, 7.0)
FRONT_HUB = (23.0, 7.0)
BB = (9.0, 6.0)                 # bottom bracket (crank axle)
SEAT_CLUSTER = (7.0, 18.5)
SADDLE = (6.3, 20.4)
HEAD_TOP = (20.0, 19.0)
HEAD_BOT = (20.8, 15.5)
STEM = (22.4, 20.4)
CRANK = 3.5
HIP = (7.6, 22.4)


@dataclass(frozen=True)
class Look:
    """Everything that changes how the rider and bike are drawn (a pose, a
    helmet color...). The cached sprites are keyed on it, so a new look is a
    field here plus a branch in draw_rider_shape(); the cache takes care of
    the rest. Change it with dataclasses.replace(scene.look, field=value), or
    for a moment from an effect's apply() via f.look."""
    lift: int = 0           # wheelie: index into LIFT_ANGLES


# ---------------------------------------------------------------------------
# The city
# ---------------------------------------------------------------------------

def draw_clouds(cv, scroll):
    for y in range(min(3, cv.h)):
        for x in range(cv.w):
            wx = int(x + scroll * 0.08)
            r = rnd(wx // 6, y, 7)
            if r < 0.35:
                cv.put(x, y, "~" if rnd(wx, y) < 0.6 else "-", "cloud")


_BUILDINGS = []     # (start, width, index), generated as the street scrolls
_BUILDING_ENDS = []


WINDOW_FLASH = 0.12     # seconds a window glows white when switched on
PARALLAX = 0.35         # the buildings scroll at this fraction of the street's speed


def ensure_buildings(x):
    """Generate buildings until the skyline reaches skyline-coordinate x."""
    while not _BUILDINGS or _BUILDINGS[-1][0] < x:
        i = len(_BUILDINGS)
        start = _BUILDINGS[-1][0] + _BUILDINGS[-1][1] + 1 + int(rnd(i - 1, 3) * 3) if i else 0
        width = 8 + int(rnd(i, 1) * 10)
        _BUILDINGS.append((start, width, i))
        _BUILDING_ENDS.append(start + width)


def building_top(i, horizon):
    """Row of building i's roof line."""
    return horizon - int(horizon * (0.3 + 0.5 * rnd(i, 2)))


def skyline_roofs(w, scroll, horizon):
    """For each screen column, the roof row of the building there (None in a gap)."""
    off = scroll * PARALLAX
    ensure_buildings(off + w)
    roofs = [None] * w
    for start, width, i in _BUILDINGS[bisect.bisect_left(_BUILDING_ENDS, off):]:
        x0 = int(start - off)
        if x0 >= w:
            break
        for x in range(max(0, x0), min(w, x0 + width)):
            roofs[x] = building_top(i, horizon)
    return roofs


def draw_buildings(cv, scroll, horizon, scene, t):
    off = scroll * PARALLAX
    ensure_buildings(off + cv.w)
    first = bisect.bisect_left(_BUILDING_ENDS, off)
    flashing = t - scene.windows_lit_at < WINDOW_FLASH
    visible = scene.visible_windows = []
    for start, width, i in _BUILDINGS[first:]:
        x0 = int(start - off)
        if x0 >= cv.w:
            break
        top = building_top(i, horizon)
        for x in range(x0, x0 + width):
            cv.put(x, top, "_", "bldg")
        for y in range(top + 1, horizon):
            cv.put(x0, y, "|", "bldg")
            cv.put(x0 + width - 1, y, "|", "bldg")
            if (y - top) % 2 == 0:
                for x in range(x0 + 2, x0 + width - 2, 3):
                    window = (i, x - x0, y - top)
                    lit = scene.windows.get(window)
                    if lit is None:                     # never switched: as built
                        lit = rnd(*window) < 0.45
                    if 0 <= x < cv.w:
                        visible.append((window, lit))
                    if not lit:
                        cv.put(x, y, ".", "windark")
                    elif flashing and window in scene.windows_just_lit:
                        cv.put(x, y, "#", "bolt")
                    else:
                        cv.put(x, y, "#", "win")


_SPECKLE = {}


def road_speckle(wx, horizon, h):
    """Rows with a speck of grit in this road column (repeats every 600 columns)."""
    key = (wx % 600, horizon, h)
    if key not in _SPECKLE:
        _SPECKLE[key] = [y for y in range(horizon + 1, h) if rnd(key[0], y, 3) < 0.05]
    return _SPECKLE[key]


def lamp_positions(cv, scroll):
    spacing = 46
    first = -int(scroll) % spacing - spacing
    return [x for x in range(first, cv.w + spacing, spacing)]


def lamp_bulbs(cv, scroll, horizon):
    """Screen positions of the street lamp bulbs."""
    top = horizon - max(6, int(horizon * 0.55))
    return [(x + 3, top + 1) for x in lamp_positions(cv, scroll)]


def draw_lamps(cv, scroll, horizon):
    height = max(6, int(horizon * 0.55))
    for x in lamp_positions(cv, scroll):
        top = horizon - height
        for y in range(top + 1, horizon):
            cv.put(x, y, "|", "curb")
        cv.text(x, top, "|__", "curb")
        cv.put(x + 3, top + 1, "V", "lamp")


def draw_lamp_glow(cv, scroll, horizon):
    for bulb_x, bulb_y in lamp_bulbs(cv, scroll, horizon):
        for y in range(bulb_y + 1, horizon + 3):
            spread = (y - bulb_y) * 0.55
            for xx in range(int(bulb_x - spread), int(bulb_x + spread) + 1):
                ch = cv.get(xx, y)
                if ch in ("/", "'", "|") and y < horizon:
                    cv.recolor(xx, y, "lamp")        # rain sparkles in the light
                elif ch == " " and rnd(xx, y, 5) < 0.18:
                    cv.put(xx, y, ".", "glow")


_DROPS = {}


def rain_drops(w, h, horizon, front):
    """Per-drop constants, worked out once per terminal size."""
    key = (w, h, horizon, front)
    if key not in _DROPS:
        drops = []
        for i in range(w * h // 40):
            if (i % 6 == 0) != front:
                continue
            drops.append((rnd(i, 1) * (w + 40), 30 + rnd(i, 2) * 18,
                          horizon + 1 + int(rnd(i, 3) * max(1, h - horizon - 1)), rnd(i, 4),
                          "/" if i % 4 else "'", "rain" if i % 3 else "rain2"))
        _DROPS[key] = drops
    return _DROPS[key]


def draw_drops(cv, t, scroll, horizon, front, wind=0.0):
    """Background drops, or (front=True) the few that fall in front of the rider.
    Wind slants the rain toward the horizontal and, while it blows, doubles it."""
    slant = 0.45 + 2.5 * wind
    streak = wind > 0.4
    drops = rain_drops(cv.w, cv.h, horizon, front)
    passes = (t, t + 0.37) if wind > 0 else (t,)    # the second pass: extra drops
    for tt in passes:
        for x0, speed, land, start, ch, color in drops:
            cycle = land + 5
            y = (start * cycle + tt * speed) % cycle
            x = (x0 - y * slant - scroll) % (cv.w + 40) - 20
            if y < land:
                if streak:
                    cv.put(x, y, "-", color)
                    cv.put(x + 1, y, "-", color)
                else:
                    cv.put(x, y, ch, color)
                continue
            if front:
                continue
            sx = (x0 - land * slant - scroll) % (cv.w + 40) - 20
            age = y - land
            if age < 1.5:
                cv.put(sx, land, "o", color)
            elif age < 3:
                cv.put(sx - 1, land, ".", color)
                cv.put(sx + 1, land, ".", color)


def draw_bolt(cv, x, y, seed, horizon, branch=False):
    """A jagged bolt from (x, y) down to a rooftop or the horizon."""
    drift = -1 if rnd(seed, 2) < 0.5 else 1
    end = min(horizon, y + 3 + int(rnd(seed, 1) * 4)) if branch else horizon
    forks = []
    while y < end:
        if y > 2 and cv.get(x, y) != " ":
            break                                   # hit a roof (or a lamp)
        r = rnd(seed, y, 3)
        if branch:
            dx = drift if r < 0.7 else 0
        else:
            dx = -1 if r < 0.35 else 1 if r > 0.65 else 0
        cv.put(x, y, "|" if dx == 0 else "/" if dx < 0 else "\\", "lamp" if branch else "bolt")
        if not branch and y > 3 and rnd(seed, y, 4) < 0.14:
            forks.append((x, y + 1, seed * 31 + y))
        x += dx
        y += 1
    for fx, fy, fseed in forks:                     # side branches, drawn after the trunk
        side = -1 if rnd(fseed, 2) < 0.5 else 1
        draw_bolt(cv, fx + side * 2, fy, fseed, horizon, branch=True)


# ---------------------------------------------------------------------------
# Effects (started by the scene's actions, below)
# ---------------------------------------------------------------------------

class Lightning(Effect):
    """A bolt from the clouds to a rooftop at a random spot, flashing the sky."""
    layer = "sky"           # behind the street, rain and rider
    duration = 0.5

    def __init__(self, t0, x=None, seed=None):
        super().__init__(t0)
        self.x = random.random() if x is None else x        # fraction of the width
        self.seed = random.randrange(1, 1 << 30) if seed is None else seed

    @staticmethod
    def visible(age):
        """Lightning flickers: a bright stroke, a gap, a return stroke, a last flicker."""
        return age < 0.10 or 0.18 < age < 0.34 or 0.44 < age < 0.50

    def draw(self, cv, f):
        age = f.t - self.t0
        if not (0 <= age and self.visible(age)):
            return
        draw_bolt(cv, int(self.x * cv.w), 0, self.seed, f.horizon)
        if age < 0.10:                                # the whole sky lights up
            for y in range(f.horizon):
                for x in range(cv.w):
                    if cv.colors[y][x] in ("cloud", "bldg", "windark"):
                        cv.recolor(x, y, "bolt" if y < 3 else "lane")


class LampFlash(Effect):
    """A sharp flash from every street lamp: full brightness at once, then a fast fade."""
    layer = "rain"          # over the normal lamp glow, so the rain sparkles too
    duration = 0.3

    def draw(self, cv, f):
        age = f.t - self.t0
        if age < 0:
            return
        p = (1 - age / self.duration) ** 2                  # 1 at the hit, then decays
        hot = "bolt" if p > 0.4 else "lamp"
        for bulb_x, bulb_y in lamp_bulbs(cv, f.scroll, f.horizon):
            cv.put(bulb_x, bulb_y, "@" if p > 0.4 else "*", hot)
            if p > 0.25:                                # a burst of rays round the bulb
                cv.put(bulb_x - 1, bulb_y, "-", hot)
                cv.put(bulb_x + 1, bulb_y, "-", hot)
            if p > 0.5:
                cv.put(bulb_x - 2, bulb_y + 1, "/", "lamp")
                cv.put(bulb_x + 2, bulb_y + 1, "\\", "lamp")
            # a wider, denser cone of light
            for y in range(bulb_y + 1, f.horizon + 3):
                spread = (y - bulb_y) * 0.55 * (1 + 0.6 * p)
                for x in range(int(bulb_x - spread), int(bulb_x + spread) + 1):
                    ch = cv.get(x, y)
                    if ch in ("/", "'", "|") and y < f.horizon:
                        cv.recolor(x, y, hot)
                    elif ch == "." and cv.colors[y][x] == "glow":
                        cv.recolor(x, y, hot)
                    elif ch == " " and rnd(x, y, 6) < 0.45 * p:
                        cv.put(x, y, ".", hot)


class ColorHit(Effect):
    """The whole scene snaps to one color for a beat, then dissolves back."""
    layer = "front"         # last, so it colors everything
    duration = 0.35
    hold = 0.12             # seconds at full strength before dissolving
    colors = ("helmet", "jacket", "frame", "bolt")   # red, orange, teal, white
    count = 0               # presses so far: each hit takes the next color

    def __init__(self, t0):
        super().__init__(t0)
        self.color = self.colors[ColorHit.count % len(self.colors)]
        ColorHit.count += 1
        self.seed = random.randrange(1, 1 << 30)

    def draw(self, cv, f):
        age = f.t - self.t0
        if age < 0:
            return
        keep = 1.0 if age < self.hold else 1 - (age - self.hold) / (self.duration - self.hold)
        for y, (chars, colors) in enumerate(zip(cv.chars, cv.colors)):
            for x, ch in enumerate(chars):
                if ch != " " and (keep >= 1 or rnd(x, y, self.seed) < keep):
                    colors[x] = self.color


class Car(Effect):
    """An oncoming car tears past in the near lane, headlights blazing."""
    layer = "front"
    duration = 0.8
    BODY = ("    _______    ",
            " __/[__][__]\\__",
            "@__(o)____(o)_]")
    PAINT = ("    bbbbbbb    ",      # b body, w windows, t tires, L headlight
             " bbbwwwwwwwwbbb",
             "Lbbtttbbbbtttbb")
    INKS = {"b": "helmet", "w": "rain2", "t": "tire", "L": "bolt"}

    def __init__(self, t0):
        super().__init__(t0)
        self.seed = random.randrange(1, 1 << 30)

    def draw(self, cv, f):
        age = f.t - self.t0
        if age < 0:
            return
        x0 = int(cv.w + 5 - (cv.w + 40) * age / self.duration)
        bottom = min(cv.h - 1, f.lane_y + 1)
        top = bottom - len(self.BODY) + 1
        # headlight beam ahead (to the left), flickering through the rain
        for d in range(1, 9):
            if rnd(d, int(f.t * 30), self.seed) < 0.85 - d * 0.07:
                cv.put(x0 - d, bottom, "=" if d < 5 else "-", "bolt" if d < 4 else "lamp")
        for r, (row, paint) in enumerate(zip(self.BODY, self.PAINT)):
            for c, (ch, ink) in enumerate(zip(row, paint)):
                if ch != " ":
                    cv.put(x0 + c, top + r, ch, self.INKS[ink])
        # tail-light streak and a spray of water behind
        tail = x0 + len(self.BODY[-1])
        for d in range(12):
            if d % 3 != 2:
                cv.put(tail + d, bottom - 1, "-", "helmet")
        for i in range(14):
            sx = tail + int(rnd(i, 1, self.seed) * 14)
            sy = bottom - int(rnd(i, 2, self.seed, int(f.t * 12)) * 3)
            cv.put(sx, sy, ".,'`"[i % 4], "rain" if i % 3 else "rain2")


class Wheelie(Effect):
    """The rider pops the front wheel up for a beat."""
    layer = None            # changes the rider's Look; draws nothing itself
    duration = 0.55

    def apply(self, f):
        age = f.t - self.t0
        lift = 2 if 0.06 <= age < 0.4 else 1 if 0 <= age < self.duration else 0
        if lift > f.look.lift:
            f.look = replace(f.look, lift=lift)


class Gust(Effect):
    """A gust of wind: the rain doubles and blows nearly sideways."""
    layer = None            # sets f.wind, which the rain and spray read
    duration = 0.6

    def apply(self, f):
        age = f.t - self.t0
        if age < 0:
            return
        wind = min(1.0, age / 0.05) * (1 - age / self.duration) ** 1.5
        f.wind = max(f.wind, wind)


class UFO(Effect):
    """A flying saucer (characters/ufo.py) swoops in, hovers about searching
    with its spotlight, then beams up someone standing on a rooftop and zips away."""
    layer = "sky"           # among the buildings: the rain and rider pass in front
    ARRIVE, SEARCH, SPOT, BEAM, LEAVE = 1.0, 3.5, 4.3, 6.0, 6.8   # phase end times (s)
    LIFT = (4.6, 5.8)       # the person rises up the beam between these times
    duration = LEAVE
    SPOTS = ("side", "roof", "front", "behind")     # where the person is standing
    SHIRTS = ("helmet", "jacket", "pack", "frame", "pants", "rain", "win", "bolt", "lane")

    def __init__(self, t0):
        super().__init__(t0)
        self.seed = random.randrange(1, 1 << 30)
        self.plan = None

    def make_plan(self, f):
        """Where it hovers and whom it takes, decided on the first frame (needs the layout)."""
        rng = random.Random(self.seed)
        w, horizon = f.w, f.horizon
        hover = (rng.uniform(1, w - ufo.WIDTH - 1), rng.randint(1, max(1, int(horizon * 0.3))))
        side = rng.choice((-1, 1))
        enter = (-14 if side < 0 else w + 3, -4)

        # The person stands among the buildings, which scroll by slowly, so pick
        # where they'll be when the beam switches on: clear of the rider, and
        # still on screen after drifting left while they're lifted.
        tempo = f.scene.tempo
        roof_speed = tempo.bpm / 60.0 * COLS_PER_REV * PARALLAX
        drift = roof_speed * (self.LIFT[1] - self.SPOT)
        spans = [(drift + 1, f.bx - 7 * f.s - 4),                   # left of the rider
                 (f.bx + 34 * f.s + 2 + drift, w - 4)]              # right of him
        spot = rng.choice(self.SPOTS)
        if spot == "side":              # scrolls in from the right edge, on a roof
            spans = [(max(spans[1][0], w - roof_speed * self.SPOT + 2), w - 4)]
        spans = [(lo, hi) for lo, hi in spans if lo < hi] or [(w - 4, w - 4)]
        lo, hi = rng.choices(spans, weights=[hi - lo + 1 for lo, hi in spans])[0]
        px = rng.uniform(lo, hi)
        off = tempo.beats(self.t0 + self.SPOT) * COLS_PER_REV * PARALLAX
        wx = px + off                   # in skyline coordinates
        ensure_buildings(wx + 40)
        start, width, i = min(_BUILDINGS, key=lambda b: abs(b[0] + b[1] / 2 - wx))
        on_building = min(max(wx, start + 1), start + width - 4)
        if spot != "front" and not drift + 1 <= on_building - off <= w - 4:
            spot = "front"              # that building would carry them off screen
        if spot == "front":             # at street level, in front of the buildings
            feet = horizon - 1
        else:                           # on a roof, or behind one with just a head showing
            wx = on_building
            feet = building_top(i, horizon) + (1 if spot == "behind" else 0)
        self.plan = hover, enter, side, wx, feet, spot, rng.choice(self.SHIRTS)

    def position(self, age, f, person_x, feet):
        """Top-left corner of the saucer at this age."""
        hover, enter, side = self.plan[:3]
        over = (person_x + 1 - 5, max(0, feet - 9))     # centered over the person
        if age < self.ARRIVE:
            k = 1 - (1 - age / self.ARRIVE) ** 2        # fast in, easing to a stop
            return enter[0] + (hover[0] - enter[0]) * k, enter[1] + (hover[1] - enter[1]) * k
        if age < self.SEARCH:
            return self.searching(age - self.ARRIVE, f.w)
        if age < self.SPOT:
            a = self.searching(self.SEARCH - self.ARRIVE, f.w)
            k = smoothstep((age - self.SEARCH) / (self.SPOT - self.SEARCH))
            return a[0] + (over[0] - a[0]) * k, a[1] + (over[1] - a[1]) * k
        if age < self.BEAM:
            return over
        k = ((age - self.BEAM) / (self.LEAVE - self.BEAM)) ** 2     # accelerating away
        return over[0] + side * 40 * k, over[1] - (over[1] + 8) * k

    def searching(self, u, w):
        """Drifting and bobbing about the hover spot, as if scanning the ground."""
        hover = self.plan[0]
        x = hover[0] + 5 * math.sin(u * 2.2) + 2 * math.sin(u * 5.1)
        y = hover[1] + (1 if math.sin(u * 3.0) > 0.6 else 0)
        return min(max(x, 0), w - ufo.WIDTH), y

    def draw(self, cv, f):
        if self.plan is None:
            self.make_plan(f)
        age = f.t - self.t0
        if age < 0:
            return
        _, _, _, wx, feet0, spot, shirt = self.plan
        person_x = int(round(wx - f.scroll * PARALLAX))
        x, y = self.position(age, f, person_x, feet0)
        x, y = int(round(x)), int(round(y))
        bottom = ufo.beam_source(x, y)[1]

        put = cv.put
        if spot == "behind":            # the buildings hide the person and the beam's foot
            roofs = skyline_roofs(cv.w, f.scroll, f.horizon)

            def put(x_, y_, ch, color):
                x_, y_ = int(round(x_)), int(round(y_))
                if not (0 <= x_ < cv.w and roofs[x_] is not None and roofs[x_] <= y_ < f.horizon):
                    cv.put(x_, y_, ch, color)

        if self.ARRIVE <= age < self.SEARCH:            # the searchlight sweeps about
            ufo.draw_searchlight(cv, x, y, math.sin((age - self.ARRIVE) * 3.0), f.t, self.seed)
        if self.SPOT <= age < self.BEAM:                # the tractor beam
            ufo.draw_beam(cv, x, y, feet0, f.t, put)

        # the person: standing, arms up once the beam hits, then lifted away
        if age < self.LIFT[1]:
            rise = smoothstep((age - self.LIFT[0]) / (self.LIFT[1] - self.LIFT[0]))
            feet = int(round(feet0 - rise * (feet0 - bottom - 1)))
            flail = self.SPOT <= age and int(f.t * 10) % 2
            arms = "\\|/" if age >= self.SPOT else "/|\\"
            legs = "| |" if flail else "/ \\"
            for dy, part, color in ((-2, " o ", "skin"), (-1, arms, shirt), (0, legs, "pants")):
                if feet + dy > bottom or rise == 0:     # swallowed into the hull
                    for dx, ch in enumerate(part):
                        if ch != " ":
                            put(person_x + dx, feet + dy, ch, color)

        ufo.draw_saucer(cv, x, y, f.t)


# ---------------------------------------------------------------------------
# The rider
# ---------------------------------------------------------------------------

class Rider(Projector):
    """Projects rider/bike units onto the terminal grid with the rear wheel's
    contact patch at column bx, just above row gy. `tilt` (radians) leans the
    whole bike back about the rear hub: a wheelie."""

    def __init__(self, cv, bx, gy, s, tilt=0.0):
        super().__init__(cv, bx, gy - 1, s, tilt, pivot=REAR_HUB, materials=cyclist.MATERIALS)

    def wheel(self, hub, spin):
        for k in range(6):                       # spokes
            a = spin + k * math.pi / 3
            self.line(add(hub, polar(1.2, a)), add(hub, polar(WHEEL_R - 1.0, a)), "curb")
        self.arc(hub, WHEEL_R, 0, 2 * math.pi, "tire")             # tire
        hx, hy = self.to_screen(hub)
        self.cv.put(hx, hy, "o", "metal")


_SPRITES = SpriteCache()


def rider_sprite(phase, s, look):
    """The rider and bike at one pedal position, as (dx, dy, char, color) cells
    relative to the bike's anchor. Rendered once, then reused every revolution.
    Anything that changes the drawing must be in the key (put it in Look) or be
    drawn live in draw_rider(), or it will be stuck at its first-seen state."""
    def render():
        bx, gy = int(12 * s) + 4, int(22 * s) + 4     # room for a wheelie
        cv = Canvas(int(44 * s) + 16, gy + 2)
        f = phase / PHASES
        # spokes repeat every 60 degrees: pick a whole number of repeats per
        # revolution close to how far the wheel really rolls in one revolution
        roll = SCROLL_SPEED * 60.0 / DEFAULT_BPM / s / WHEEL_R
        spin = -f * max(1, round(roll / (math.pi / 3))) * math.pi / 3
        draw_rider_shape(cv, bx, gy, s, -f * 2 * math.pi, spin, int(f * 22), look)
        return cells_from_canvas(cv, bx, gy)
    return _SPRITES.get((phase, look), s, render)


def draw_rider_shape(cv, bx, gy, s, crank, spin, links, look):
    R = Rider(cv, bx, gy, s, math.radians(LIFT_ANGLES[look.lift]))
    bob = 0.3 * math.sin(2 * crank)

    def leg(pedal, near):
        ankle = add(pedal, (-0.4, 1.3))
        knee = solve_joint(HIP, ankle, THIGH, SHIN)     # knees point forward
        toe = add(ankle, (3.0, -0.9 + 0.5 * math.sin(crank + (0 if near else math.pi))))
        return (HIP, knee, ankle, add(ankle, (-0.6, -0.2)), toe)

    near_pedal = add(BB, polar(CRANK, crank))
    far_pedal = add(BB, polar(CRANK, crank + math.pi))
    shoulder = (17.4, 29.4 + bob)
    j = Joints(
        spine=(add(HIP, (0.2, 1.4)), shoulder),
        neck=add(shoulder, (1.0, 0.5)),
        head=(21.6, 32.2 + bob),
        shoulder=shoulder,
        elbow=(20.0, 24.6 + bob * 0.5),
        hand=(23.4, 20.8),
        legs=(leg(far_pedal, near=False), leg(near_pedal, near=True)),
        pack=((10.0, 28.4 + bob), (13.6, 30.8 + bob)),
    )

    # behind the bike: the far leg and far crank
    R.solids(cyclist.far_parts(j))
    R.line(BB, far_pedal, "tire")

    # the bike
    R.wheel(REAR_HUB, spin)
    R.wheel(FRONT_HUB, spin)
    R.line(REAR_HUB, BB, "frame")                        # chainstay
    R.line(REAR_HUB, SEAT_CLUSTER, "frame")              # seat stay
    R.line(BB, SEAT_CLUSTER, "frame")                    # seat tube
    R.line(SEAT_CLUSTER, HEAD_TOP, "frame")              # top tube
    R.line(BB, HEAD_BOT, "frame")                        # down tube
    R.line(HEAD_TOP, HEAD_BOT, "frame")                  # head tube
    R.line(HEAD_BOT, FRONT_HUB, "frame")                 # fork
    R.line(SEAT_CLUSTER, SADDLE, "metal")                # seat post
    R.line(add(SADDLE, (-2.4, 0.5)), add(SADDLE, (2.0, 0.2)), "shoe", "=")   # saddle
    R.line(HEAD_TOP, STEM, "metal")                      # stem
    R.line(STEM, (24.4, 20.4), "metal")                  # bars
    R.arc((24.0, 19.0), 1.4, math.radians(80), math.radians(-90), "metal")    # drop
    # chain: moving links between chainring and cog
    for (a, b) in (((BB[0], BB[1] + 2.3), (REAR_HUB[0], REAR_HUB[1] + 1.2)),
                   ((BB[0], BB[1] - 2.3), (REAR_HUB[0], REAR_HUB[1] - 1.2))):
        sa, sb = R.to_screen(a), R.to_screen(b)
        n = int(abs(sb[0] - sa[0])) + 1
        for i in range(n + 1):
            f = i / n
            cv.put(sa[0] + (sb[0] - sa[0]) * f, sa[1] + (sb[1] - sa[1]) * f,
                   ":" if (i + links) % 2 else "-", "metal")
    R.arc(REAR_HUB, 1.2, 0, 2 * math.pi, "metal")         # cog
    R.arc(BB, 2.3, 0, 2 * math.pi, "metal")               # chainring
    # in front of the bike: the near leg, body, head and arm
    R.solids(cyclist.near_parts(j))
    cyclist.draw_face(cv, R, j)
    # reflective stripe on the backpack
    R.line((10.2, 29.6 + bob), (13.4, 31.6 + bob), "lamp", "=")


def rear_spray(R, t, wind=0.0):
    """A rooster tail of water flicked up by the back wheel; wind streaks it out."""
    for i in range(18):
        age = (t * 2.4 + i / 18.0) % 1.0
        vx, vy = (-10.0 - rnd(i, 1) * 8) * (1 + 2 * wind), 6.0 + rnd(i, 2) * 8
        p = (-WHEEL_R * 0.6 + vx * age * 0.7, 2.5 + vy * age * 0.7 - 14 * age * age * 0.49)
        if p[1] < 0:
            continue
        sx, sy = R.to_screen(p)
        R.cv.put(sx, sy, ".,'`"[i % 4], "rain" if i % 3 else "rain2")


def head_beam(cv, hx, hy, t):
    """Headlight cone shining forward (right) through the rain."""
    reach = 44
    for d in range(1, reach):
        x = hx + d
        spread = int(d * 0.22)
        fade = 1.0 - d / reach
        for y in range(hy - spread // 3, hy + spread + 1):
            ch = cv.get(x, y)
            if ch is None:
                continue
            if ch in ("/", "'", "o", "."):
                cv.recolor(x, y, "lamp")
            elif ch == " " and rnd(x, y, int(t * 20)) < 0.25 * fade:
                cv.put(x, y, "-" if y == hy else ".", "lamp")


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------

class RainyRide(Scene):
    name = "rainy_ride"
    description = "Cartoon ASCII bike ride in the rain"
    palette = PALETTE
    min_size = (60, 22)
    default_bpm = DEFAULT_BPM
    bpm_help = "pedal revolutions per minute"
    loading_message = "Getting the bike ready..."
    goodbye = "Home and dry. \U0001F6B2"
    layers = [
        "sky",          # clouds, buildings, street lamps
        "street",       # curb, lane markings, puddles
        "rain",         # rain behind the rider, lamp glow
        "rider",        # spray, bike and rider, headlight
        "front",        # the few drops in front of the rider
        "hud",          # the tempo readout, over everything
    ]

    def __init__(self, args=None):
        super().__init__(args)
        self.look = Look()
        self.windows = {}               # window -> lit, where switched
        self.visible_windows = []       # (window, lit) on screen now
        self.windows_lit_at = -1e9      # when the last switch turned windows on
        self.windows_just_lit = frozenset()     # the windows it turned on

    def layout(self, f):
        w, h = f.w, f.h
        f.gy = int(h * 0.82)                        # row just below the wheels
        f.horizon = f.gy - max(9, int(h * 0.28))
        f.lane_y = min(h - 1, f.gy + max(1, (h - f.gy) // 2))
        f.s = max(0.7, min(2.6, min(h / 30.0, w / 80.0)))   # rider scale
        f.bx = int(w * 0.33)                        # rear wheel's column
        f.scroll = f.beats * COLS_PER_REV           # how far the street has slid by
        # things effects may change for this frame only (in Effect.apply)
        f.look = self.look                          # how the rider is drawn
        f.wind = 0.0                                # 0 calm .. 1 a full gust

    def warm_up(self, f):
        """Render every pose up front, so the first wheelie doesn't stutter."""
        for lift in range(len(LIFT_ANGLES)):
            for phase in range(PHASES):
                rider_sprite(phase, f.s, Look(lift=lift))

    def prepare_still(self, t):
        if os.environ.get("BOLT"):
            self.add_effect(Lightning(t - 0.05, x=0.6, seed=12345))

    # --- layers ------------------------------------------------------------

    def draw_sky(self, cv, f):
        draw_clouds(cv, f.scroll)
        draw_buildings(cv, f.scroll, f.horizon, self, f.t)
        draw_lamps(cv, f.scroll, f.horizon)

    def draw_street(self, cv, f):
        scroll, horizon, lane_y, t = f.scroll, f.horizon, f.lane_y, f.t
        for x in range(cv.w):
            wx = int(x + scroll)
            cv.put(x, horizon, "=", "curb")
            if wx % 12 < 6:
                cv.put(x, lane_y, "=", "lane")
            for y in road_speckle(wx, horizon, cv.h):
                if y != lane_y:
                    cv.put(x, y, ".", "road")
        # puddles, fixed to the road, with rain rings flickering on them
        for x in range(-20, cv.w + 20):
            wx = int(x + scroll)
            if wx % 37 == 0 and rnd(wx, 9) < 0.7:
                y = horizon + 2 + int(rnd(wx, 10) * max(1, cv.h - horizon - 3))
                if y == lane_y:
                    y += 1
                length = 5 + int(rnd(wx, 11) * 6)
                for k in range(length):
                    ripple = rnd(wx + k, int(t * 6)) < 0.15
                    cv.put(x + k, y, "o" if ripple else "~", "puddle")

    def draw_rain(self, cv, f):
        draw_drops(cv, f.t, f.scroll, f.horizon, front=False, wind=f.wind)
        draw_lamp_glow(cv, f.scroll, f.horizon)

    def draw_rider(self, cv, f):
        """The cached rider and bike, plus the parts that change every frame."""
        bx, gy, s, t = f.bx, f.gy, f.s, f.t
        rear_spray(Rider(cv, bx, gy, s), t, f.wind)      # off the road, so never tilted
        R = Rider(cv, bx, gy, s, math.radians(LIFT_ANGLES[f.look.lift]))
        phase = int(f.beats * PHASES) % PHASES
        stamp(cv, rider_sprite(phase, s, f.look), bx, gy)
        hx, hy = R.to_screen((25.2, 21.2))           # headlight glows
        head_beam(cv, int(hx) + 1, int(round(hy)), t)
        cv.put(hx, hy, "@", "lamp")

    def draw_front(self, cv, f):
        draw_drops(cv, f.t, f.scroll, f.horizon, front=True, wind=f.wind)

    def draw_hud(self, cv, f):
        label = "%g BPM" % round(self.tempo.bpm, 1)
        cv.text(cv.w - len(label) - 1, cv.h - 1, label, "lane")

    # --- actions -----------------------------------------------------------

    @action("lightning", keys="l")
    def strike_lightning(self, t):
        self.add_effect(Lightning(t))

    @action("lamp_flash", keys="a")
    def flash_lamps(self, t):
        self.add_effect(LampFlash(t))

    @action("switch_windows", keys="s")
    def switch_windows(self, t):
        """Flip exactly half of the windows on screen, all at once."""
        visible = list(self.visible_windows)
        random.shuffle(visible)
        flip = len(visible) // 2
        # only on-screen windows are kept: the ones that scrolled away never return
        self.windows = {window: lit != (n < flip) for n, (window, lit) in enumerate(visible)}
        self.windows_just_lit = frozenset(window for window, lit in visible[:flip] if not lit)
        self.windows_lit_at = t

    @action("color_hit", keys="d")
    def color_hit(self, t):
        self.add_effect(ColorHit(t))

    @action("car", keys="f")
    def car(self, t):
        self.add_effect(Car(t))

    @action("wheelie", keys="g")
    def wheelie(self, t):
        self.add_effect(Wheelie(t))

    @action("gust", keys="h")
    def gust(self, t):
        self.add_effect(Gust(t))

    @action("ufo", keys="j")
    def ufo(self, t):
        self.add_effect(UFO(t))


if __name__ == "__main__":
    run(RainyRide)
