"""Scenes, effects and actions: the parts a new animation is built from.

A Scene draws itself in LAYERS, back to front: for each name in `layers`
its draw_<name>(cv, f) method runs, then the active effects whose `layer`
matches draw on top. Inputs trigger named actions (methods marked with
@action, mapped from keys); an action changes the scene or starts an Effect.
"""

from .canvas import Canvas
from .terminal import color_codes


class Tempo:
    """A beat clock. Everything that moves in time with the music follows
    beats(t), so a tempo change never makes anything jump."""

    def __init__(self, bpm, min_bpm=1, max_bpm=400):
        self.bpm = bpm                      # change it with set_bpm(), not directly
        self.min_bpm, self.max_bpm = min_bpm, max_bpm
        self.beats_at_change = 0.0          # beats done when the bpm last changed
        self.changed_at = 0.0               # ...and when that was

    def beats(self, t):
        """Beats done by time t."""
        return self.beats_at_change + (t - self.changed_at) * self.bpm / 60.0

    def set_bpm(self, bpm, t):
        self.beats_at_change = self.beats(t)
        self.changed_at = t
        self.bpm = min(self.max_bpm, max(self.min_bpm, bpm))


class Frame:
    """The layout and timing of one frame, handed to every draw function.
    Scenes add their own layout fields in Scene.layout(); effects may change
    per-frame settings on it in Effect.apply()."""

    def __init__(self, w, h, t, scene):
        self.w, self.h, self.t, self.scene = w, h, t, scene
        self.beats = scene.tempo.beats(t)


class Effect:
    """Something temporary: drawn into one layer of the scene until it's
    done, and/or changing this frame's settings in apply()."""
    layer = None            # which layer it's drawn after (None: not drawn)
    duration = 1.0          # seconds until it's removed

    def __init__(self, t0):
        self.t0 = t0

    def age(self, f):
        return f.t - self.t0

    def done(self, t):
        return t - self.t0 >= self.duration

    def apply(self, f):
        """Change this frame's settings before anything is drawn."""

    def draw(self, cv, f):
        raise NotImplementedError


def action(name, keys=()):
    """Decorator for a Scene method handler(self, t): registers it as action
    `name`, triggered by `keys` (characters, or "up"/"down"/"left"/"right")."""
    def mark(handler):
        handler._action = (name, tuple(keys))
        return handler
    return mark


class Scene:
    """Subclass this to make an animation. See termanim/__init__.py."""
    name = None             # what play.py calls it (defaults to the module name)
    description = ""
    palette = {}            # color name -> xterm-256 index
    layers = ()             # layer names, back to front: each needs a draw_<name>(cv, f)
    frame_class = Frame
    min_size = (1, 1)       # smallest terminal (columns, rows) it can draw in
    fps = 24
    default_bpm = 60
    bpm_help = "beats per minute"
    min_bpm, max_bpm = 1, 400
    loading_message = None  # shown while warm_up() runs
    goodbye = None          # printed after the animation stops

    actions = {}            # action name -> method name, collected from @action
    keymap = {}             # key -> action name

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        actions, keymap = {}, {}
        for klass in reversed(cls.__mro__):         # subclasses override their bases
            for attr, value in vars(klass).items():
                spec = getattr(value, "_action", None)
                if spec:
                    name, keys = spec
                    actions[name] = attr
                    for k in keys:
                        keymap[k] = name
        cls.actions, cls.keymap = actions, keymap

    def __init__(self, args=None):
        bpm = getattr(args, "bpm", None)
        self.tempo = Tempo(self.default_bpm if bpm is None else bpm, self.min_bpm, self.max_bpm)
        self.effects = []
        self.codes = color_codes(self.palette)

    @classmethod
    def add_arguments(cls, parser):
        """Add scene-specific command line options."""

    # --- input -----------------------------------------------------------------

    def add_effect(self, effect):
        self.effects.append(effect)
        return effect

    def trigger(self, name, t):
        """Run action `name` at time t. Any input (keys, MIDI...) comes through here."""
        getattr(self, self.actions[name])(t)

    def press(self, key, t):
        """Handle a key; returns whether it was mapped to an action."""
        name = self.keymap.get(key) or self.keymap.get(key.lower())
        if name:
            self.trigger(name, t)
        return bool(name)

    @action("bpm_up", keys=["up"])
    def bpm_up(self, t):
        self.tempo.set_bpm(self.tempo.bpm + 1, t)

    @action("bpm_down", keys=["down"])
    def bpm_down(self, t):
        self.tempo.set_bpm(self.tempo.bpm - 1, t)

    # --- drawing ---------------------------------------------------------------

    def too_small(self, w, h):
        return w < self.min_size[0] or h < self.min_size[1]

    def layout(self, f):
        """Work out this frame's layout and defaults, as fields on f."""

    def warm_up(self, f):
        """Pre-render anything slow before the animation starts."""

    def prepare_still(self, t):
        """Called before --still renders a single frame at time t (for debugging)."""

    def update(self, t):
        """Called once per frame before drawing: drops finished effects."""
        self.effects = [e for e in self.effects if not e.done(t)]

    def make_frame(self, w, h, t):
        f = self.frame_class(w, h, t, self)
        self.layout(f)
        return f

    def build_frame(self, w, h, t):
        cv = Canvas(w, h)
        f = self.make_frame(w, h, t)
        for effect in self.effects:
            effect.apply(f)
        for name in self.layers:
            getattr(self, "draw_" + name)(cv, f)
            for effect in self.effects:
                if effect.layer == name:
                    effect.draw(cv, f)
        return cv
