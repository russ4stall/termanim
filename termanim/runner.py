"""Running a scene: command line options, the frame loop, and key input.

Built to run smoothly on slow machines and over SSH: after the first frame
only the cells that changed are sent to the terminal. A keypress is drawn
straight away rather than at the next frame tick, so effects land on the
beat when played along to music.
"""

import argparse
import sys
import time

from .terminal import (ALT_SCREEN_OFF, ALT_SCREEN_ON, CLEAR, HIDE_CURSOR, HOME, RESET,
                       SHOW_CURSOR, keyboard, read_keys, terminal_size)


def make_parser(scene_cls, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=scene_cls.description)
    parser.add_argument("--fps", type=float, default=scene_cls.fps,
                        help="frames per second (default %g)" % scene_cls.fps)
    parser.add_argument("--mono", action="store_true", help="no color")
    parser.add_argument("--bpm", type=float, default=scene_cls.default_bpm,
                        help="%s (default %g)" % (scene_cls.bpm_help, scene_cls.default_bpm))
    parser.add_argument("--bench", type=int, metavar="N",
                        help="render N frames off-screen and print the frame rate")
    parser.add_argument("--still", type=float, help=argparse.SUPPRESS)  # debug: one frame at time T
    scene_cls.add_arguments(parser)
    return parser


def frame_text(scene, w, h, t, codes):
    if scene.too_small(w, h):
        msg = "Make the window bigger (at least %dx%d)" % scene.min_size
        lines = [" " * w] * (h // 2) + [msg.center(w)[:w]]
        return "\r\n".join(lines + [" " * w] * (h - len(lines)))
    return scene.build_frame(w, h, t).render(codes)


def bench(scene, n, fps, codes, parser):
    w, h = terminal_size()
    if scene.too_small(w, h):
        parser.error("terminal too small to benchmark (at least %dx%d)" % scene.min_size)
    start = time.time()
    prev, full_bytes, diff_bytes = None, 0, 0
    for i in range(n):
        cv = scene.build_frame(w, h, i / fps)
        full = cv.render(codes)
        full_bytes += len(full.encode())
        diff_bytes += len((cv.render_diff(prev, codes) if prev else full).encode())
        prev = cv
    took = time.time() - start
    print("%d frames at %dx%d in %.2fs: %.1f fps (including warm-up)"
          % (n, w, h, took, n / took))
    print("output per frame: full redraw %.1f KB, changes only %.1f KB "
          "(%.0f KB/s at %g fps)" % (full_bytes / n / 1024, diff_bytes / n / 1024,
                                      diff_bytes / n / 1024 * fps, fps))


def run(scene_cls, argv=None, prog=None):
    """Parse the command line and play scene_cls in the terminal until Ctrl+C."""
    parser = make_parser(scene_cls, prog)
    args = parser.parse_args(argv)
    if args.bpm <= 0:
        parser.error("--bpm must be positive")
    scene = scene_cls(args)
    codes = None if args.mono else scene.codes

    if args.bench:
        bench(scene, args.bench, args.fps, codes, parser)
        return

    if args.still is not None:
        w, h = terminal_size()
        scene.prepare_still(args.still)
        sys.stdout.write(frame_text(scene, w, h - 1, args.still, codes) + "\n")
        return

    delay = 1.0 / max(args.fps, 1)
    out = sys.stdout
    with keyboard() as fd:
        w, h = terminal_size()
        if not scene.too_small(w, h):
            if scene.loading_message:
                out.write(scene.loading_message + "\n")
                out.flush()
            scene.warm_up(scene.make_frame(w, h, 0))
        out.write(ALT_SCREEN_ON + HIDE_CURSOR + CLEAR)
        start = time.time()
        last_size = None
        prev = None                         # last frame drawn, for sending only changes
        next_tick = 0.0                     # when the next regular frame is due
        try:
            while True:
                frame_start = time.time()
                t = frame_start - start
                if frame_start >= next_tick:
                    next_tick = frame_start + delay
                w, h = terminal_size()
                if (w, h) != last_size:
                    out.write(CLEAR)
                    last_size, prev = (w, h), None
                scene.update(t)
                if scene.too_small(w, h):
                    out.write(HOME + frame_text(scene, w, h, t, codes))
                    prev = None
                else:
                    cv = scene.build_frame(w, h, t)
                    out.write(cv.render_diff(prev, codes) if prev else HOME + cv.render(codes))
                    prev = cv
                out.flush()
                # wait for the next tick, but a keypress cuts the wait short and is
                # drawn at once, so effects land on the beat; ticks stay on schedule
                pause = max(0.0, next_tick - time.time())
                if fd is None:
                    time.sleep(pause)
                    continue
                for key in read_keys(fd, pause):
                    scene.press(key, time.time() - start)
        except KeyboardInterrupt:
            pass
        finally:
            out.write(RESET + SHOW_CURSOR + ALT_SCREEN_OFF)
            if scene.goodbye:
                out.write(scene.goodbye + "\n")
            out.flush()
