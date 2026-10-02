"""Drawing figures in "units" and projecting them onto the character grid.

Shapes are described in units: x to the right, y up. One unit is one column
wide at scale 1, and a terminal row is `aspect` units tall (character cells
are about 2:1). Thin things (tubes, spokes) are drawn as lines and arcs of
slope characters; solid things are built from Parts (capsules and ellipses,
as signed distance functions) and shaded with a brightness ramp.
"""

import math

RAMP = ".:-=+*#%@"              # body shading, dark -> bright
LIGHT = (0.35, 0.94)            # light from above and slightly ahead


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def mul(a, s):
    return (a[0] * s, a[1] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def lerp(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)


def length(a):
    return math.hypot(a[0], a[1])


def polar(r, ang):
    return (r * math.cos(ang), r * math.sin(ang))


def solve_joint(root, end, upper, lower, bend=1):
    """Two-bone inverse kinematics: where the middle joint (a knee, an elbow)
    goes for bones of these lengths to reach from root to end. It bends
    toward +x (bend=1) or -x (bend=-1)."""
    d = sub(end, root)
    dist = min(max(length(d), 1e-3), (upper + lower) * 0.999)
    dn = mul(d, 1.0 / max(length(d), 1e-3))
    a = (upper * upper - lower * lower + dist * dist) / (2 * dist)
    h = math.sqrt(max(upper * upper - a * a, 0.0))
    perp = (-dn[1], dn[0])
    if perp[0] * bend < 0:
        perp = (dn[1], -dn[0])
    return add(add(root, mul(dn, a)), mul(perp, h))


def sd_capsule(p, a, b, r):
    pa, ba = sub(p, a), sub(b, a)
    h = max(0.0, min(1.0, (pa[0] * ba[0] + pa[1] * ba[1]) / (ba[0] * ba[0] + ba[1] * ba[1])))
    return length(sub(pa, mul(ba, h))) - r


def sd_ellipse(p, c, rx, ry):
    """Approximate signed distance to an axis-aligned ellipse."""
    q = ((p[0] - c[0]) / rx, (p[1] - c[1]) / ry)
    k = length(q)
    return (k - 1.0) * min(rx, ry)


class Part:
    """A solid, shaded piece of a figure: a capsule ("cap", (a, b, radius))
    or an ellipse ("ell", (center, rx, ry)), in a material."""

    def __init__(self, kind, args, mat, clip_below=None):
        self.kind, self.args, self.mat, self.clip_below = kind, args, mat, clip_below

    def sdf(self, p):
        if self.kind == "cap":
            d = sd_capsule(p, *self.args)
        else:
            d = sd_ellipse(p, *self.args)
        if self.clip_below is not None:          # keep only the part above this height
            d = max(d, self.clip_below - p[1])
        return d

    def bounds(self):
        if self.kind == "cap":
            a, b, r = self.args
            return (min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)
        c, rx, ry = self.args
        return (c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry)


class Shell(Part):
    """An ellipse turned to lie along `axis` (a unit vector), optionally cut
    flat: `cut` is (point, normal) and only the side the normal points to is
    kept. Turn it with a figure's head, say, and a helmet turns too."""

    def __init__(self, center, along, across, axis, mat, cut=None):
        super().__init__("ell", (center, along, across), mat)
        self.axis, self.cut = axis, cut

    def sdf(self, p):
        c, ra, rb = self.args
        d = sub(p, c)
        u, v = dot(d, self.axis), d[1] * self.axis[0] - d[0] * self.axis[1]
        dist = (math.hypot(u / ra, v / rb) - 1) * min(ra, rb)
        if self.cut:
            dist = max(dist, -dot(sub(p, self.cut[0]), self.cut[1]))
        return dist

    def bounds(self):
        (cx, cy), ra, rb = self.args
        r = max(ra, rb)
        return cx - r, cy - r, cx + r, cy + r


class Projector:
    """Projects units onto the canvas and draws in them. Unit (0, 0) lands
    on cell (ox, oy); `tilt` (radians) rotates everything about `pivot`.
    `materials` maps a Part's material to (light color, dark color, brightness)."""

    def __init__(self, cv, ox, oy, s, tilt=0.0, pivot=(0.0, 0.0), materials=None,
                 aspect=2.0, ramp=RAMP, light=LIGHT):
        self.cv, self.ox, self.oy, self.s = cv, ox, oy, s
        self.tilt, self.cos, self.sin = tilt, math.cos(tilt), math.sin(tilt)
        self.pivot, self.materials, self.aspect = pivot, materials or {}, aspect
        self.ramp, self.light = ramp, light

    def rot(self, v, sign=1):
        """Rotate a direction by the tilt (sign=-1: undo it)."""
        if not self.tilt:
            return v
        c, s_ = self.cos, self.sin * sign
        return (v[0] * c - v[1] * s_, v[0] * s_ + v[1] * c)

    def to_screen(self, p):
        if self.tilt:
            p = add(self.pivot, self.rot(sub(p, self.pivot)))
        return self.ox + p[0] * self.s, self.oy - p[1] * self.s / self.aspect

    def to_units(self, col, row):
        p = (col - self.ox) / self.s, (self.oy - row) * self.aspect / self.s
        if self.tilt:
            p = add(self.pivot, self.rot(sub(p, self.pivot), -1))
        return p

    # --- thin things: tubes, spokes, chains --------------------------------

    @staticmethod
    def slope_char(dx, dy):
        """Line character for a direction given in units (y up)."""
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        if ang < 24 or ang >= 156:
            return "-"
        if ang < 66:
            return "/"
        if ang < 114:
            return "|"
        return "\\"

    def line(self, a, b, color, ch=None):
        sa, sb = self.to_screen(a), self.to_screen(b)
        n = int(max(abs(sb[0] - sa[0]), abs(sb[1] - sa[1])) * 2) + 1
        c = ch or self.slope_char(*self.rot(sub(b, a)))
        for i in range(n + 1):
            f = i / n
            self.cv.put(sa[0] + (sb[0] - sa[0]) * f, sa[1] + (sb[1] - sa[1]) * f, c, color)

    def arc(self, c, r, a0, a1, color, ch=None):
        steps = max(8, int(abs(a1 - a0) * r * self.s * 1.5))
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            p = add(c, polar(r, a))
            c_ = ch or self.slope_char(*self.rot((-math.sin(a), math.cos(a))))
            if c_ == "|":                       # round off the sides
                c_ = ")" if math.cos(a) > 0 else "("
            sx, sy = self.to_screen(p)
            self.cv.put(sx, sy, c_, color)

    # --- solid things --------------------------------------------------------

    def solids(self, parts):
        """Draw Parts shaded and outlined; later parts are in front."""
        if not parts:
            return
        bxs = [p.bounds() for p in parts]
        x0 = min(b[0] for b in bxs) - 1
        y0 = min(b[1] for b in bxs) - 1
        x1 = max(b[2] for b in bxs) + 1
        y1 = max(b[3] for b in bxs) + 1
        corners = [self.to_screen(c) for c in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))]
        c0, c1 = min(c[0] for c in corners), max(c[0] for c in corners)
        r0, r1 = min(c[1] for c in corners), max(c[1] for c in corners)
        edge = 0.7 / self.s
        eps = 0.25
        ramp, light = self.ramp, self.light
        for row in range(int(r0) - 1, int(r1) + 2):
            for col in range(int(c0) - 1, int(c1) + 2):
                p = self.to_units(col, row)
                hit, near, near_d = None, None, 1e9
                for part in parts:                     # later parts are in front
                    d = part.sdf(p)
                    if d < 0:
                        hit = part
                    elif d < near_d:
                        near, near_d = part, d
                if hit is not None:
                    n = self.rot(self.normal(hit, p, eps))
                    lum = 0.2 + 0.8 * max(0.0, n[0] * light[0] + n[1] * light[1])
                    depth = min(1.0, -hit.sdf(p) * self.s * 0.7)
                    lum = lum * (0.55 + 0.45 * depth)
                    lit, dark, bright = self.materials[hit.mat]
                    lum *= bright
                    ch = ramp[int(min(0.999, lum) * len(ramp))]
                    self.cv.put(col, row, ch, lit if lum > 0.42 else dark)
                elif near is not None and near_d < edge:
                    # outline: an edge character following the silhouette
                    n = self.rot(self.normal(near, p, eps))
                    self.cv.put(col, row, self.edge_char(n), self.materials[near.mat][1])

    @staticmethod
    def normal(part, p, eps):
        dx = part.sdf((p[0] + eps, p[1])) - part.sdf((p[0] - eps, p[1]))
        dy = part.sdf((p[0], p[1] + eps)) - part.sdf((p[0], p[1] - eps))
        n = math.hypot(dx, dy) or 1.0
        return dx / n, dy / n

    @staticmethod
    def edge_char(n):
        nx, ny = n
        if abs(ny) > 2.2 * abs(nx):
            return "_" if ny > 0 else "-"
        if abs(nx) > 2.2 * abs(ny):
            return "|"
        return "\\" if nx * ny > 0 else "/"
