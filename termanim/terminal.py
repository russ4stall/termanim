"""Talking to the terminal: escape codes, its size, and raw key input."""

import contextlib
import os
import select
import shutil
import sys

try:
    import termios
    import tty
except ImportError:         # no raw keyboard input (e.g. Windows)
    termios = tty = None

# ANSI escape codes
ALT_SCREEN_ON = "\033[?1049h"
ALT_SCREEN_OFF = "\033[?1049l"
CLEAR = "\033[2J"
HOME = "\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
RESET = "\033[0m"


def color_codes(palette):
    """Escape codes for a palette of name -> xterm-256 index (None resets)."""
    codes = {name: "\033[38;5;%dm" % code for name, code in palette.items()}
    codes[None] = RESET
    return codes


def terminal_size():
    size = shutil.get_terminal_size((100, 30))
    return size.columns, size.lines


@contextlib.contextmanager
def keyboard():
    """Read keys without Enter while inside; Ctrl+C still works. Yields the
    file descriptor to pass to read_keys(), or None if there's no keyboard."""
    fd = sys.stdin.fileno() if sys.stdin.isatty() and termios else None
    saved_tty = termios.tcgetattr(fd) if fd is not None else None
    if fd is not None:
        tty.setcbreak(fd)
    try:
        yield fd
    finally:
        if saved_tty is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved_tty)


ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}


def read_keys(fd, timeout):
    """Keys pressed within `timeout` seconds: characters, or "up", "down",
    "left", "right" for the arrow keys. Other escape sequences are dropped."""
    ready, _, _ = select.select([fd], [], [], timeout)
    data = os.read(fd, 64).decode(errors="ignore") if ready else ""
    keys, i = [], 0
    while i < len(data):
        if data.startswith(("\033[", "\033O"), i) and i + 2 < len(data):
            j = i + 2               # parameters run up to a final byte in @..~
            while j < len(data) - 1 and not "@" <= data[j] <= "~":
                j += 1
            if j == i + 2 and data[j] in ARROWS:
                keys.append(ARROWS[data[j]])
            i = j + 1
        else:
            keys.append(data[i])
            i += 1
    return keys
