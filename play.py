#!/usr/bin/env python3
"""
Play a scene from scenes/.

    python3 play.py                         # list the scenes and their keys
    python3 play.py rainy_ride --bpm 120    # play one (scene options: --help)
"""

import importlib
import inspect
import pkgutil
import sys

import scenes
from termanim import Scene, run


def find_scenes():
    """Scene name -> Scene subclass, for every scene defined in scenes/."""
    found = {}
    for info in pkgutil.iter_modules(scenes.__path__):
        module = importlib.import_module("scenes." + info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, Scene) and cls.__module__ == module.__name__:
                found[cls.name or info.name] = cls
    return found


def describe(name, cls):
    keys = {}
    for key, act in cls.keymap.items():
        keys.setdefault(act, []).append(key)
    print("  %-14s %s" % (name, cls.description))
    for act, ks in keys.items():
        print("  %14s   %-10s %s" % ("", "/".join(ks), act))


def main():
    found = find_scenes()
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip() + "\n\nScenes:")
        for name, cls in sorted(found.items()):
            describe(name, cls)
        return
    name = sys.argv[1]
    if name not in found:
        sys.exit("No scene called %r. Try one of: %s" % (name, ", ".join(sorted(found))))
    run(found[name], sys.argv[2:], prog="play.py " + name)


if __name__ == "__main__":
    main()
