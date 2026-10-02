"""
The cyclist: a rider in a red helmet, orange rain jacket and blue trousers.

He is built from shaded shapes (termanim.shading Parts) in units, x to the
right and y up. A scene poses him by filling in Joints, then draws him:

    R = Projector(cv, x, y, s, materials=cyclist.MATERIALS)
    R.solids(cyclist.far_parts(j))      # the far leg, behind everything
    ...                                 # anything between his legs (a bike)
    R.solids(cyclist.near_parts(j))     # body, head, near leg and arm
    cyclist.draw_face(cv, R, j)

Changes to how he looks go here, so every scene he's in keeps up.
"""

from dataclasses import dataclass

from termanim.shading import Part, Shell, add, mul

# His colors (xterm-256 indices), to merge into a scene's palette.
COLORS = {
    "skin": 223, "jacket": 208, "jacket_dk": 166, "pants": 33, "pants_dk": 18,
    "shoe": 236, "helmet": 160, "pack": 65, "metal": 250,
}

MATERIALS = {   # light color, dark color, brightness
    "jacket": ("jacket", "jacket_dk", 1.0),
    "skin": ("skin", "skin", 1.3),
    "arm": ("jacket", "jacket_dk", 0.8),
    "pants": ("pants", "pants_dk", 1.0),
    "pants_far": ("pants_dk", "pants_dk", 0.55),
    "shoe": ("metal", "shoe", 0.8),
    "helmet": ("helmet", "helmet", 1.0),
    "pack": ("pack", "pack", 0.9),
}

# Proportions, in units
THIGH, SHIN = 11.4, 10.6        # bone lengths, for posing legs with solve_joint
TORSO_R = 2.8
HEAD_R = 3.0
NECK_R = 1.3
UPPER_ARM_R, FOREARM_R = 1.6, 1.3
THIGH_R, SHIN_R, SHOE_R = 1.75, 1.3, 1.05
PACK_R = 1.9


@dataclass(frozen=True)
class Joints:
    """A pose: where his joints are, in units."""
    spine: tuple            # torso, hip end to shoulder end (a capsule between each pair)
    neck: tuple             # where his neck leaves his shoulders
    head: tuple             # center of his head
    shoulder: tuple         # where the near arm starts
    elbow: tuple
    hand: tuple
    legs: tuple             # (hip, knee, ankle, heel, toe) for the far leg, then the near
    fwd: tuple = (1.0, 0.0)     # the way his face points (unit vector)
    up: tuple = (0.0, 1.0)      # toward the crown of his head (unit vector)
    chest: float = TORSO_R      # torso radius (more when breathing in)
    pack: tuple = None          # (bottom, top) of his backpack, or None without it

    def at(self, along_face, toward_crown):
        """A point on his head, in the head's own directions."""
        return add(self.head, add(mul(self.fwd, along_face), mul(self.up, toward_crown)))


def leg_parts(leg, near):
    hip, knee, ankle, heel, toe = leg
    mat = "pants" if near else "pants_far"
    return [Part("cap", (hip, knee, THIGH_R), mat),
            Part("cap", (knee, ankle, SHIN_R), mat),
            Part("cap", (heel, toe, SHOE_R), "shoe")]


def far_parts(j):
    """The far leg: drawn first, behind his body (and behind a bike)."""
    return leg_parts(j.legs[0], near=False)


def near_parts(j):
    """Everything else, back to front: torso, backpack, head, near leg, near arm."""
    parts = [Part("cap", (a, b, j.chest), "jacket") for a, b in zip(j.spine, j.spine[1:])]
    if j.pack:
        parts.append(Part("cap", (j.pack[0], j.pack[1], PACK_R), "pack"))
    parts += [
        Part("cap", (j.neck, j.at(-1.2, -0.8), NECK_R), "skin"),
        Part("ell", (j.head, HEAD_R, HEAD_R), "skin"),
        Part("ell", (j.at(2.9, -0.5), 1.0, 0.9), "skin"),                          # nose
        Shell(j.at(-0.6, 0.7), 3.8, 3.2, j.fwd, "helmet",
              (add(j.head, mul(j.up, -0.1)), j.up)),                                # helmet
        Part("cap", (j.at(2.6, 1.2), j.at(4.2, 0.8), 0.55), "helmet"),              # visor
    ]
    parts += leg_parts(j.legs[1], near=True)
    parts += [
        Part("cap", (j.shoulder, j.elbow, UPPER_ARM_R), "arm"),
        Part("cap", (j.elbow, j.hand, FOREARM_R), "arm"),
        Part("ell", (add(j.hand, (0.3, 0.0)), 1.3, 1.2), "shoe"),                  # glove
    ]
    return parts


def draw_face(cv, R, j, eye="o", mouth="-"):
    """His eye and mouth, drawn over his head with projector R."""
    ex, ey = R.to_screen(j.at(1.4, 0.0))
    cv.put(ex, ey, eye, "shoe")
    mx, my = R.to_screen(j.at(2.0, -1.6))
    cv.put(mx, my, mouth, "jacket_dk")
