"""
The alien: a big domed green head with huge slanted purple eyes, on a skinny neck.

Drawn with its top-left corner at (x, y) in screen cells:

    alien.draw(cv, x, y, blink=False, neck=8, bottom=table_row)
"""

# Its colors (xterm-256 indices), to merge into a scene's palette.
COLORS = {"alien": 120, "alien_dk": 28, "alien_eye": 93, "alien_glint": 231}

HEAD = ("   .-'''-.   ",
        " .'       '. ",
        "/  _     _  \\",
        "| (o@\\ /@o) |",
        "|  `-' `-'  |",
        " \\   ' '   / ",
        "  '.  -  .'  ",
        "    `---'    ")
PAINT = ("   ggggggg   ",      # g skin and outline, d creases and features, e eye, w glint
         " gg       gg ",
         "g  d     d  g",
         "g dwed dewd g",
         "g  ddd ddd  g",
         " g   d d   g ",
         "  gg  d  gg  ",
         "    ggggg    ")
INKS = {"g": "alien", "d": "alien_dk", "e": "alien_eye", "w": "alien_glint"}
NECK = ("     | |     ", "     d d     ")
WIDTH, HEIGHT = len(HEAD[0]), len(HEAD)
EYE_ROW, EYES = 3, (2, 11)  # the row its eyes are on, and the columns they span


def draw(cv, x, y, blink=False, neck=0, bottom=None):
    """The head, then `neck` rows of neck below it, stopping above row
    `bottom` (when it's peeking up from behind something)."""
    rows = list(zip(HEAD, PAINT)) + [NECK] * neck
    for r, (row, paint) in enumerate(rows):
        if bottom is not None and y + r >= bottom:
            break
        inside = len(row) - len(row.lstrip()), len(row.rstrip())
        for c, (ch, ink) in enumerate(zip(row, paint)):
            if ink in "ew" and r == EYE_ROW and blink:
                cv.put(x + c, y + r, "-", "alien")      # eyelids shut
            elif ch != " ":
                cv.put(x + c, y + r, ch, INKS[ink])
            elif inside[0] < c < inside[1]:             # the face hides what's behind it
                cv.put(x + c, y + r, " ")
