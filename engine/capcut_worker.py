#!/usr/bin/env python3
"""Draws one CapCut transition or effect into a ProRes 4444 movie (python3 capcut_worker.py job.json).

Runs in its own process: the drawing code (engine/capcut_lib) reads its working size from CAPCUT_W/CAPCUT_H at import.
Job fields: mode (transition | overlay | content), index (catalog position), package (folder in backend/data/capcut),
fps, frames, out, out_width, out_height; transition: a_raw, b_raw, comp (seconds of the CapCut composition);
overlay: seconds_offset, intro; content: base_raw, offset.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "capcut_lib"))
import ctrans as C  # noqa: E402
import ctrans2 as C2  # noqa: E402
import ceffects as E  # noqa: E402

FUNCS = C.FUNCS + C2.FUNCS


class Dummy:
    """A package without After Effects data (3D scenes): the drawing only needs its folder and length."""
    def __init__(self, folder, dur):
        self.root = feature_root(folder).rstrip("/")
        self.dur = dur
        self.tracks = {}
        self.d = {"ae_attribute": {}}

    def k(self, *args, **kwargs):
        return kwargs.get("default", 0.0)


def package(folder, dur):
    if list(Path(folder).glob("x/**/LumiExportData.lua")):
        return C.Pkg(str(folder) + "/")
    return Dummy(folder, dur)


def feature_root(folder):
    """The package's AmazingFeature folder (its case differs between packages)."""
    return str(next(p for p in sorted(Path(folder, "x").iterdir()) if p.is_dir() and p.name.lower() == "amazingfeature")) + "/"


def frames(path, n):
    data = np.fromfile(path, np.uint8)
    return data.reshape(n, C.H, C.W, 3)


def main():
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    n, fps = int(job["frames"]), float(job["fps"])
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pixel_format", "rgba",
           "-video_size", f"{C.W}x{C.H}", "-framerate", str(job["fps"]), "-i", "pipe:0", "-an",
           "-vf", f"scale={job['out_width']}:{job['out_height']}:flags=lanczos",
           *(["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "2M", "-auto-alt-ref", "0"] if job.get("codec") == "webm"
             else ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20"] if job.get("codec") == "mp4"
             else ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]), job["out"]]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    ones = np.ones((C.H, C.W, 1), np.float32)

    def put(rgb, alpha=None):
        a = ones if alpha is None else np.clip(alpha, 0, 1)[..., None]
        proc.stdin.write((np.clip(np.concatenate([rgb, a], 2), 0, 1) * 255 + .5).astype(np.uint8).tobytes())

    try:
        mode = job["mode"]
        if mode == "transition":
            pkg = package(job["package"], job.get("comp", 1.0))
            fn = FUNCS[job["index"]]
            a, b = frames(job["a_raw"], n), frames(job["b_raw"], n)
            for k in range(n):
                p = (k + .5) / n
                A = a[k].astype(np.float32) / 255
                B = b[k].astype(np.float32) / 255
                put(fn(pkg, A, B, p * pkg.dur))
        elif mode == "overlay":
            root = feature_root(job["package"])
            fn, _, _ = E.OVERLAYS[job["index"]]
            for k in range(n):
                t = job.get("seconds_offset", 0) + k / fps
                rgb, alpha = fn(root, t, job.get("intro", True)) if job["index"] == 9 else fn(root, t)
                put(rgb, alpha)
        elif mode == "content":
            root = feature_root(job["package"])
            fn, _ = E.CONTENT[job["index"]]
            base = frames(job["base_raw"], n)
            for k in range(n):
                put(fn(root, base[k].astype(np.float32) / 255, job.get("offset", 0) + k / fps))
        else:
            raise ValueError("unknown mode " + mode)
        proc.stdin.close()
        err = proc.stderr.read()
        if proc.wait():
            raise RuntimeError(err.decode(errors="replace")[-600:])
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        Path(job["out"]).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
