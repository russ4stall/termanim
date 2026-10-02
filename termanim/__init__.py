"""termanim: a small framework for cartoon ASCII animations in the terminal.

Writing a scene (see scenes/example.py for a complete one):

    from termanim import Scene, Effect, action, run

    class Fireflies(Scene):
        description = "Fireflies over a pond"
        palette = {"glow": 228, "water": 31}      # color name -> xterm-256 index
        layers = ["pond", "flies"]                # back to front

        def layout(self, f):                      # per-frame layout, as fields on f
            f.shore = int(f.h * 0.7)

        def draw_pond(self, cv, f): ...           # one draw_<layer>(cv, f) per layer
        def draw_flies(self, cv, f): ...

        @action("flash", keys="f")                # a key starts a temporary Effect
        def flash(self, t):
            self.add_effect(Flash(t))

    class Flash(Effect):
        layer = "flies"                           # drawn right after that layer
        duration = 0.3
        def draw(self, cv, f): ...

    if __name__ == "__main__":
        run(Fireflies)

Drop the module in scenes/ and `python3 play.py fireflies` runs it.
Every scene gets --fps, --mono, --bpm, --bench and up/down arrows for the
tempo; f.beats counts beats so motion can follow the music.
"""

from .canvas import Canvas
from .runner import run
from .scene import Effect, Frame, Scene, Tempo, action
from .util import rnd, smoothstep

__all__ = ["Canvas", "Effect", "Frame", "Scene", "Tempo", "action", "run", "rnd", "smoothstep"]
