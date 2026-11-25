#!/usr/bin/env python3
"""Draws CapCut transitions and effects into movies (ProRes 4444, or H.264 / VP9 for the editor's preview).

`python3 capcut_worker.py --serve` stays alive and takes one JSON job a line on stdin, answering one JSON line each
({"ok": true} or {"error": "..."}): numpy, scipy and the packages are imported once (about 2 s) and, started before the
sides of a seam are drawn, while they are drawn. `python3 capcut_worker.py job.json` draws one job.

The drawing code (engine/capcut_lib) reads its working size from CAPCUT_W/CAPCUT_H at import.
Job fields: mode (transition | overlay | content), index (catalog position), package (folder in engine/capcut_assets),
fps, frames, out, out_width, out_height, codec (prores | mp4 | webm); transition: a_video, b_video (the sides at the
film's size, null for an empty side), comp (seconds of the CapCut composition); overlay: seconds_offset, intro; content:
base_video (null: a sample picture, for the editor's library), offset. Sides are decoded straight into memory through a
pipe, scaled to the working size, the last frame held when a video is short: no raw frames touch the disk.
"""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "capcut_lib"))
import ctrans as C  # noqa: E402
import ctrans2 as C2  # noqa: E402
import ceffects as E  # noqa: E402

FUNCS = C.FUNCS + C2.FUNCS
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


class Dummy:
    """A package without After Effects data (3D scenes): the drawing only needs its folder and length."""
    def __init__(self, folder, dur):
        self.root = feature_root(folder).rstrip("/")
        self.dur = dur
        self.tracks = {}
        self.d = {"ae_attribute": {}}

    def k(self, *args, **kwargs):
        return kwargs.get("default", 0.0)


_PACKAGES = {}


def package(folder, dur):
    key = (str(folder), dur)
    if key not in _PACKAGES:
        _PACKAGES[key] = C.Pkg(str(folder) + "/") if list(Path(folder).glob("x/**/LumiExportData.lua")) else Dummy(folder, dur)
    return _PACKAGES[key]


def feature_root(folder):
    """The package's AmazingFeature folder (its case differs between packages)."""
    return str(next(p for p in sorted(Path(folder, "x").iterdir()) if p.is_dir() and p.name.lower() == "amazingfeature")) + "/"


def sample_frame():
    """A picture with colour, light and edges for the library's preview of an effect that changes the frame."""
    yy, xx = np.mgrid[0:C.H, 0:C.W].astype(np.float32)
    u, v = xx / C.W, yy / C.H
    rgb = np.dstack([.25 + .55 * u, .3 + .4 * (1 - v), .55 + .35 * np.sin(u * 3.1) * v]).astype(np.float32)
    disc = ((u - .62) ** 2 * (C.W / C.H) ** 2 + (v - .5) ** 2) < .06
    rgb[disc] = (.95, .85, .4)
    rgb[(v > .78) & (v < .84) & (u > .12) & (u < .5)] = 1.0
    return np.clip(rgb, 0, 1)


def side(video, n):
    """The frames of a side video at the working size, one float32 frame at a time (black when there is no side)."""
    size = C.W * C.H * 3
    if not video:
        black = np.zeros((C.H, C.W, 3), np.float32)
        for _ in range(n):
            yield black
        return
    proc = subprocess.Popen([FFMPEG, "-v", "error", "-nostdin", "-i", str(video), "-vf",
                             f"scale={C.W}:{C.H}:flags=area,tpad=stop_mode=clone:stop_duration=2", "-frames:v", str(n),
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    last = None
    try:
        for _ in range(n):
            data = proc.stdout.read(size)
            if len(data) == size:
                last = np.frombuffer(data, np.uint8).reshape(C.H, C.W, 3).astype(np.float32) / 255
            elif last is None:   # nothing decoded: the side's error, or an empty video drawn black
                if proc.wait():
                    raise RuntimeError("side: " + proc.stderr.read().decode(errors="replace")[-400:])
                last = np.zeros((C.H, C.W, 3), np.float32)
            yield last
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stderr.close()


def draw(job):
    n, fps = int(job["frames"]), float(job["fps"])
    codec = job.get("codec")
    cmd = [FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pixel_format", "rgba",
           "-video_size", f"{C.W}x{C.H}", "-framerate", str(job["fps"]), "-i", "pipe:0", "-an",
           *(["-vf", f"scale={job['out_width']}:{job['out_height']}:flags=lanczos"]
             if (job["out_width"], job["out_height"]) != (C.W, C.H) else []),
           *(["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "2M", "-auto-alt-ref", "0"] if codec == "webm"
             else ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "20"] if codec == "mp4"
             else ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]), job["out"]]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    rgba = np.empty((C.H, C.W, 4), np.float32)

    def put(rgb, alpha=None):
        rgba[..., :3] = rgb
        rgba[..., 3] = 1.0 if alpha is None else alpha
        np.clip(rgba, 0, 1, out=rgba)
        proc.stdin.write((rgba * 255 + .5).astype(np.uint8).tobytes())

    try:
        mode = job["mode"]
        if mode == "transition":
            pkg = package(job["package"], job.get("comp", 1.0))
            fn = FUNCS[job["index"]]
            # frame k of n stands for the middle of its own time: (k + .5) / n, the last one close to the incoming side
            for k, (A, B) in enumerate(zip(side(job.get("a_video"), n), side(job.get("b_video"), n))):
                put(fn(pkg, A, B, (k + .5) / n * pkg.dur))
        elif mode == "overlay":
            root = feature_root(job["package"])
            fn, _, _ = E.OVERLAYS[job["index"]]
            for k in range(n):
                t = job.get("seconds_offset", 0) + k / fps
                put(*(fn(root, t, job.get("intro", True)) if job["index"] == 9 else fn(root, t)))
        elif mode == "content":
            root = feature_root(job["package"])
            fn, _ = E.CONTENT[job["index"]]
            frames = side(job["base_video"], n) if job.get("base_video") else (sample_frame() for _ in range(n))
            for k, base in enumerate(frames):
                put(fn(root, base, job.get("offset", 0) + k / fps))
        else:
            raise ValueError("unknown mode " + mode)
        proc.stdin.close()
        err = proc.stderr.read()
        if proc.wait():
            raise RuntimeError(err.decode(errors="replace")[-600:])
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        Path(job["out"]).unlink(missing_ok=True)
        raise


def serve():
    answers = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout = sys.stderr   # a stray print of the drawing code never breaks the answers
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            draw(json.loads(line))
            answers.write('{"ok": true}\n')
        except Exception as error:   # noqa: BLE001 - the job fails, the worker stays
            answers.write(json.dumps({"error": f"{error}\n{traceback.format_exc()[-800:]}"}) + "\n")


def main():
    if sys.argv[1:] == ["--serve"]:
        serve()
    else:
        draw(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
